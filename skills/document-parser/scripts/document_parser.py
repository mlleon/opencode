from __future__ import annotations

import argparse
import json
import os
import hashlib
from importlib import import_module
from pathlib import Path
import re
import shutil
import tempfile
from datetime import datetime
from typing import List, Optional
import sys

_orchestrator = import_module("scripts.orchestrator")


_SOURCE_KIND_CHOICES = ["book", "article", "paper", "web"]

_FINAL_STEM_SHA_RE = re.compile(r"__h[0-9a-f]{12}$")


def _isHexSha12(text: str) -> bool:
  return bool(re.fullmatch(r"[0-9a-f]{12}", text))


def _sha256HexFromBytes(data: bytes) -> str:
  return hashlib.sha256(data).hexdigest()


def _sha12FromBytes(data: bytes) -> str:
  return _sha256HexFromBytes(data)[:12]


def _sha12FromFileBytes(path: Path) -> str:
  return _sha12FromBytes(path.read_bytes())


def _sha12FromStagingInputs(stagingDocRoot: Path) -> str:
  normalizedDir = stagingDocRoot / "normalized"
  docPath = normalizedDir / "document.md"
  if not docPath.exists():
    raise FileNotFoundError(f"staging 缺少 normalized/document.md：{docPath}")

  hasher = hashlib.sha256()
  docBytes = docPath.read_bytes()
  hasher.update(b"document.md\0")
  hasher.update(docBytes)

  imagesDir = normalizedDir / "images"
  if imagesDir.exists():
    for imgPath in sorted(p for p in imagesDir.rglob("*") if p.is_file()):
      rel = imgPath.relative_to(normalizedDir).as_posix()
      hasher.update(rel.encode("utf-8"))
      hasher.update(b"\0")
      hasher.update(imgPath.read_bytes())

  return hasher.hexdigest()[:12]


def _parseLegacyParseMany(argv: List[str]) -> int:
  parser = argparse.ArgumentParser(prog="document-parser")
  parser.add_argument("inputs", nargs="+", help="本地文件路径或 URL（不可混用）")
  parser.add_argument(
    "--output-dir",
    dest="outputDir",
    default=None,
    help="输出根目录；不传则使用 CWD",
  )
  try:
    args = parser.parse_args(argv)
  except SystemExit as e:
    code = e.code
    if code is None:
      return 0
    if isinstance(code, int):
      return code
    return 2

  inputs: List[str] = list(args.inputs)
  hasUrl = any(item.startswith("http") for item in inputs)
  hasLocal = any(not item.startswith("http") for item in inputs)
  if hasUrl and hasLocal:
    print("错误：不支持 URL 与本地文件混用", file=sys.stderr)
    return 2

  outputDir = Path(args.outputDir) if args.outputDir else Path.cwd()
  try:
    results = _orchestrator.parseMany(sources=inputs, outputDir=outputDir)
  except Exception as e:
    print(f"错误：{e}", file=sys.stderr)
    return 1

  for result in results:
    print(result.paths.normalizedMarkdownPath)
  return 0


def _ensureInside(baseDir: Path, path: Path) -> None:
  baseResolved = baseDir.resolve()
  pathResolved = path.resolve()
  try:
    pathResolved.relative_to(baseResolved)
  except Exception as e:
    raise ValueError(f"非法路径（越界）：{pathResolved}") from e


def _readText(path: Path) -> str:
  return path.read_text(encoding="utf-8")


def _writeText(path: Path, text: str) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text(text, encoding="utf-8")


def _normalizeNewlines(text: str) -> str:
  # plan Step 0
  text = text.replace("\r\n", "\n").replace("\r", "\n")
  lines = [line.rstrip() for line in text.split("\n")]
  return "\n".join(lines).rstrip() + "\n"


_ILLEGAL_TITLE_CHARS_RE = re.compile(r"[\\/:*?\"<>|]")


def _extractTitleFromMarkdownFirstLine(markdown: str) -> Optional[str]:
  firstLine = markdown.splitlines()[:1]
  if not firstLine:
    return None
  line = firstLine[0].strip()
  if not line.startswith("# "):
    return None
  title = line[2:].strip()
  return title or None


def _isTrustedTitle(title: str) -> bool:
  if _ILLEGAL_TITLE_CHARS_RE.search(title):
    return False
  if len(title) < 2 or len(title) > 60:
    return False
  compact = re.sub(r"\s+", "", title).strip().lower()
  noise = {"扫描版", "无标题", "document", "untitled", "章节", "目录"}
  if compact in noise:
    return False
  return True


def _sanitizeHumanStem(text: str) -> str:
  # 清洗规则：空白归一 + 替换英文冒号
  text = text.replace(":", "：")
  text = re.sub(r"\s+", " ", text).strip()
  # 去掉首尾标点与多余括号（保守做法：仅剥离常见符号）
  text = re.sub(
    r"^[\s\-—_·（）()《》【】\[\]{}\"'“”‘’\.,，。;；:：!！?？]+",
    "",
    text,
  )
  text = re.sub(
    r"[\s\-—_·（）()《》【】\[\]{}\"'“”‘’\.,，。;；:：!！?？]+$",
    "",
    text,
  )
  if not text:
    return ""

  allowedPunct = set("-_ ·（）()《》【】：")
  cleanedChars: List[str] = []
  for ch in text:
    if ch.isalnum() or ch.isspace():
      cleanedChars.append(ch)
      continue
    if ch in allowedPunct:
      cleanedChars.append(ch)
      continue
    # 允许中文等非 ASCII 字符（但禁止路径非法字符）
    if _ILLEGAL_TITLE_CHARS_RE.search(ch):
      continue
    if ord(ch) >= 0x80:
      cleanedChars.append(ch)
  cleaned = "".join(cleanedChars)
  cleaned = re.sub(r"\s+", " ", cleaned).strip()
  return cleaned


def _selectHumanStem(*, title: Optional[str], sourceFileStem: Optional[str]) -> tuple[str, Optional[str]]:
  # 返回 humanStem 以及 titleExtracted
  if title and _isTrustedTitle(title):
    stem = _sanitizeHumanStem(title)
    if stem:
      return stem, title
  if sourceFileStem:
    stem = _sanitizeHumanStem(sourceFileStem)
    if stem:
      return stem, None
  return "doc", None


def _findReusableFinalStem(*, bucketDir: Path, sha12: str) -> Optional[str]:
  if not bucketDir.exists():
    return None
  suffix = f"__h{sha12}"
  for child in bucketDir.iterdir():
    if not child.is_dir():
      continue
    if child.name.endswith(suffix):
      return child.name
  return None


def _resolveFinalStem(
  *,
  bucketDir: Path,
  sha12: str,
  title: Optional[str],
  sourceFileStem: Optional[str],
) -> tuple[str, str, Optional[str]]:
  existing = _findReusableFinalStem(bucketDir=bucketDir, sha12=sha12)
  humanStem, titleExtracted = _selectHumanStem(title=title, sourceFileStem=sourceFileStem)
  if existing:
    return existing, humanStem, titleExtracted
  safeHuman = re.sub(r"[^A-Za-z0-9\u0080-\uFFFF _\-·（）()《》【】：]+", "-", humanStem).strip(" -.")
  safeHuman = safeHuman or "doc"
  return f"{safeHuman}__h{sha12}", humanStem, titleExtracted


_MD_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
_HTML_IMAGE_RE = re.compile(r"<img\s+[^>]*src=\"([^\"]+)\"[^>]*>", re.IGNORECASE)

_OBSIDIAN_EMBED_RE = re.compile(r"!\[\[([^\]]+)\]\]")

_ALLOWED_EMBED_TARGET_RE = re.compile(
  r"^assets/raw/(books|articles|papers|web)/([^/]+)/([^/]+)$"
)


def _extractImageRefs(markdown: str) -> List[str]:
  refs = []
  for match in _MD_IMAGE_RE.finditer(markdown):
    refs.append(match.group(1))
  for match in _HTML_IMAGE_RE.finditer(markdown):
    refs.append(match.group(1))
  return refs


def _rewriteImageRefs(*, markdown: str, mapping: dict[str, str]) -> str:
  def _mdRepl(match: re.Match) -> str:
    target = match.group(1)
    if target not in mapping:
      return match.group(0)
    return f"![[{mapping[target]}]]"

  def _htmlRepl(match: re.Match) -> str:
    target = match.group(1)
    if target not in mapping:
      return match.group(0)
    return f"![[{mapping[target]}]]"

  updated = _MD_IMAGE_RE.sub(_mdRepl, markdown)
  updated = _HTML_IMAGE_RE.sub(_htmlRepl, updated)
  return updated


_HEADING_LINE_RE = re.compile(r"^(#+)\s+\S")
_STRONG_BOUNDARY_RE = re.compile(r"^(#+\s*)?第[一二三四五六七八九十百千0-9]+(卷|章|讲|回|节)\b")


def _isHeadingLine(line: str) -> bool:
  return bool(_HEADING_LINE_RE.match(line))


def _isMarkdownImageLine(line: str) -> bool:
  return bool(_MD_IMAGE_RE.search(line.strip()))


def _mergeConsecutiveHeadingBlocks(markdown: str) -> str:
  # plan Step 1：合并连续标题块。
  lines = markdown.splitlines(keepends=False)
  merged: list[str] = []

  idx = 0
  while idx < len(lines):
    line = lines[idx]
    if not _isHeadingLine(line):
      merged.append(line)
      idx += 1
      continue

    headingTexts: list[str] = []
    headingLevels: list[int] = []
    betweenLines: list[str] = []

    # 收集连续标题行，以及中间允许的空行/图片/<details>块。
    while True:
      current = lines[idx]
      match = _HEADING_LINE_RE.match(current)
      if not match:
        break
      level = len(match.group(1))
      headingLevels.append(level)
      headingTexts.append(current.strip()[level:].strip())
      idx += 1

      # 收集中间允许的内容。
      while idx < len(lines):
        peek = lines[idx]
        stripped = peek.strip()
        if stripped == "":
          betweenLines.append(peek)
          idx += 1
          continue
        if _isMarkdownImageLine(peek):
          betweenLines.append(peek)
          idx += 1
          continue
        if stripped.startswith("<details"):
          # 包含整个 <details> ... </details> 块。
          betweenLines.append(peek)
          idx += 1
          while idx < len(lines):
            betweenLines.append(lines[idx])
            if lines[idx].strip().endswith("</details>"):
              idx += 1
              break
            idx += 1
          continue
        break

      # 若下一个不是标题行，则结束连续块。
      if idx >= len(lines) or not _isHeadingLine(lines[idx]):
        break

    if len(headingTexts) <= 1:
      # 无需合并：把原标题行与 betweenLines 原样输出。
      merged.append(line)
      merged.extend(betweenLines)
      continue

    # 合并：保留最高级别（# 数量最少）并拼接文本。
    level = min(headingLevels)
    combined = " ".join(text for text in headingTexts if text).strip()
    merged.append(f"{'#' * level} {combined}" if combined else f"{'#' * level}")
    merged.extend(betweenLines)

  return "\n".join(merged).rstrip() + "\n"


def _countCandidateHeadings(markdown: str) -> int:
  # plan Step 3：候选边界=强边界 + 次强边界（不在 ToC 段内）。
  strong, secondary, _ = _extractBoundaryCandidates(markdown)
  return len(strong) + len(secondary)


def _detectTocRanges(markdown: str) -> list[dict[str, int]]:
  # plan Step 2：目录段识别（仅禁用边界触发，不移动文本）。
  lines = markdown.splitlines()
  tocTitleIndexes: list[int] = []
  for idx, line in enumerate(lines):
    stripped = line.strip()
    if not stripped:
      continue
    if not _isHeadingLine(stripped):
      continue
    title = re.sub(r"^#+\s+", "", stripped).strip()
    if title in {"目录", "目 录"}:
      tocTitleIndexes.append(idx)

  def _isTocLine(text: str) -> bool:
    lineText = text.strip()
    if not lineText:
      return False
    if len(lineText) > 80:
      return False
    hasDots = bool(re.search(r"\.{2,}", lineText))
    hasPageNum = bool(re.search(r"\b\d{1,4}\b", lineText)) and ("。" not in lineText)
    return hasDots or hasPageNum

  ranges: list[dict[str, int]] = []
  for titleIdx in tocTitleIndexes:
    scanStart = titleIdx + 1
    scanEndMax = min(len(lines), scanStart + 200)
    windowEnd = min(len(lines), scanStart + 60)

    hits = 0
    for i in range(scanStart, windowEnd):
      if _isTocLine(lines[i]):
        hits += 1

    if hits < 15:
      continue

    # 目录段成立：向下扩展，直到 5 行连续非 ToC 或 200 行上限。
    consecutiveNon = 0
    endIdx = scanStart
    for i in range(scanStart, scanEndMax):
      if _isTocLine(lines[i]):
        consecutiveNon = 0
        endIdx = i
      else:
        consecutiveNon += 1
        if consecutiveNon >= 5:
          break
        endIdx = i

    if endIdx >= scanStart:
      ranges.append({"startLine": scanStart + 1, "endLine": endIdx + 1})

  return ranges


def _isLineInRanges(lineNo1: int, ranges: list[dict[str, int]]) -> bool:
  for item in ranges:
    if item["startLine"] <= lineNo1 <= item["endLine"]:
      return True
  return False


def _extractBoundaryCandidates(markdown: str) -> tuple[list[int], list[int], list[dict[str, int]]]:
  tocRanges = _detectTocRanges(markdown)
  lines = markdown.splitlines()

  strong: list[int] = []
  secondary: list[int] = []

  noise = {"目录", "前言", "图书在版编目", "[no text]"}

  for idx, line in enumerate(lines):
    lineNo1 = idx + 1
    if _isLineInRanges(lineNo1, tocRanges):
      continue

    stripped = line.strip()
    if not stripped:
      continue

    if _STRONG_BOUNDARY_RE.match(stripped):
      strong.append(idx)
      continue

    if not _isHeadingLine(stripped):
      continue

    headingText = re.sub(r"^#+\s+", "", stripped).strip()
    compact = re.sub(r"\s+", "", headingText).strip().lower()
    if compact in {re.sub(r"\s+", "", item).strip().lower() for item in noise}:
      continue

    if len(headingText) < 2 or len(headingText) > 30:
      continue

    secondary.append(idx)

  return strong, secondary, tocRanges


def _selectBreakIndex(text: str, *, minPos: int, maxPos: int) -> int:
  # chunk 模式切分点优先级：空行 > 标题行 > 句号/分号 > 硬切。
  if maxPos <= minPos:
    return maxPos

  window = text[minPos:maxPos]

  # 1) 空行：寻找最后一个 "\n\n" 边界。
  blankIdx = window.rfind("\n\n")
  if blankIdx != -1:
    return minPos + blankIdx + 2

  # 2) 标题行：寻找最后一个行首标题。
  headingMatches = list(re.finditer(r"(?m)^#+\s+", window))
  if headingMatches:
    return minPos + headingMatches[-1].start()

  # 3) 句号/分号：寻找最后一个断句符。
  punctIdx = max(window.rfind("。"), window.rfind("；"))
  if punctIdx != -1:
    return minPos + punctIdx + 1

  # 4) 硬切
  return maxPos


def _splitByChunks(*, text: str, targetMin: int, targetMax: int) -> list[tuple[int, int]]:
  ranges: list[tuple[int, int]] = []
  pos = 0
  textLen = len(text)

  while pos < textLen:
    remaining = textLen - pos
    if remaining <= targetMax:
      ranges.append((pos, textLen))
      break

    minPos = pos + targetMin
    maxPos = min(pos + targetMax, textLen)
    cut = _selectBreakIndex(text, minPos=minPos, maxPos=maxPos)
    if cut <= pos:
      cut = maxPos
    ranges.append((pos, cut))
    pos = cut

  return ranges


def _splitBookMarkdown(
  *,
  markdown: str,
) -> tuple[str, list[dict], list[dict[str, int]], int, int]:
  # 返回 splitMode, chunksMeta, tocRanges, strongCount, candidateCount。
  markdown = _normalizeNewlines(markdown)
  markdown = _mergeConsecutiveHeadingBlocks(markdown)
  strongCandidates, secondaryCandidates, tocRanges = _extractBoundaryCandidates(markdown)

  strongCount = len(strongCandidates)
  candidateCount = strongCount + len(secondaryCandidates)

  if 3 <= strongCount <= 200:
    splitMode = "chapter"
  elif candidateCount > 300:
    splitMode = "chunk"
  else:
    splitMode = "chunk"

  chunks: list[dict] = []

  if splitMode == "chapter":
    boundaries = sorted(strongCandidates)
    lines = markdown.splitlines(keepends=True)
    # 以行索引边界拆分，生成 char offset。
    lineCharStarts: list[int] = []
    acc = 0
    for line in lines:
      lineCharStarts.append(acc)
      acc += len(line)

    # 将边界行索引转为 charStart。
    starts: list[int] = [0]
    for lineIdx in boundaries:
      if lineIdx <= 0:
        continue
      starts.append(lineCharStarts[lineIdx])
    starts = sorted(set(starts))
    ranges: list[tuple[int, int]] = []
    for i, start in enumerate(starts):
      end = starts[i + 1] if i + 1 < len(starts) else len(markdown)
      ranges.append((start, end))

    # 小章合并（向后）
    mergedRanges: list[tuple[int, int]] = []
    idx = 0
    while idx < len(ranges):
      start, end = ranges[idx]
      fragment = markdown[start:end]
      lineCount = fragment.count("\n")
      if (len(fragment) < 1200 or lineCount < 30) and (idx + 1 < len(ranges)):
        nextStart, nextEnd = ranges[idx + 1]
        mergedRanges.append((start, nextEnd))
        idx += 2
        continue
      mergedRanges.append((start, end))
      idx += 1

    # 大章二切（按 chunk 规则）
    finalRanges: list[tuple[int, int]] = []
    for start, end in mergedRanges:
      fragmentLen = end - start
      if fragmentLen > 40000:
        subRanges = _splitByChunks(text=markdown[start:end], targetMin=15000, targetMax=25000)
        for subStart, subEnd in subRanges:
          finalRanges.append((start + subStart, start + subEnd))
      else:
        finalRanges.append((start, end))

    for fileIndex, (start, end) in enumerate(finalRanges, start=1):
      preview = markdown[start : min(end, start + 120)].replace("\n", " ").strip()
      chunks.append(
        {
          "fileName": f"ch-{fileIndex:02d}.md",
          "charStart": start,
          "charEnd": end,
          "preview": preview,
        }
      )
    return splitMode, chunks, tocRanges, strongCount, candidateCount

  # chunk 模式
  ranges = _splitByChunks(text=markdown, targetMin=15000, targetMax=25000)
  # 安全阀：文件数 <= 100（plan 测试约束）
  if len(ranges) > 100:
    step = (len(ranges) + 100 - 1) // 100
    mergedRanges: list[tuple[int, int]] = []
    for i in range(0, len(ranges), step):
      start = ranges[i][0]
      end = ranges[min(len(ranges) - 1, i + step - 1)][1]
      mergedRanges.append((start, end))
    ranges = mergedRanges[:100]

  for fileIndex, (start, end) in enumerate(ranges, start=1):
    preview = markdown[start : min(end, start + 120)].replace("\n", " ").strip()
    chunks.append(
      {
        "fileName": f"ch-{fileIndex:02d}.md",
        "charStart": start,
        "charEnd": end,
        "preview": preview,
      }
    )
  return splitMode, chunks, tocRanges, strongCount, candidateCount


def _getBuckets(sourceKind: str) -> tuple[str, str]:
  # 返回 (rawSubdir, assetsBucket)
  if sourceKind == "book":
    return "04-books", "books"
  if sourceKind == "article":
    return "01-articles", "articles"
  if sourceKind == "paper":
    return "02-papers", "papers"
  if sourceKind == "web":
    return "07-web", "web"
  raise ValueError(f"未知 sourceKind: {sourceKind}")


def _prepareAssetsMapping(
  *,
  stagingNormalizedDir: Path,
  markdown: str,
  assetsBucket: str,
  finalStem: str,
) -> tuple[str, List[str], dict[str, str]]:
  refs = _extractImageRefs(markdown)
  uniqueRefs = sorted(set(refs))
  mapping: dict[str, str] = {}

  imagesOutRelDir = f"assets/raw/{assetsBucket}/{finalStem}"
  for idx, ref in enumerate(uniqueRefs, start=1):
    normalizedRef = ref
    if normalizedRef.startswith("./"):
      normalizedRef = normalizedRef[2:]
    if not normalizedRef.startswith("images/"):
      raise ValueError(f"不支持的图片引用（必须位于 images/）：{ref}")
    srcPath = stagingNormalizedDir / normalizedRef
    if not srcPath.exists():
      raise FileNotFoundError(f"图片引用指向不存在的文件：{ref} -> {srcPath}")
    ext = srcPath.suffix.lower() or ".bin"
    dstName = f"img-{idx:04d}{ext}"
    dstRel = f"{imagesOutRelDir}/{dstName}"
    mapping[ref] = dstRel
    mapping[normalizedRef] = dstRel
    mapping[f"./{normalizedRef}"] = dstRel

  rewritten = _rewriteImageRefs(markdown=markdown, mapping=mapping)
  rewritten = _normalizeNewlines(rewritten)
  if _MD_IMAGE_RE.search(rewritten) or _HTML_IMAGE_RE.search(rewritten):
    raise ValueError("图片引用重写未完成：终态 raw 不允许出现 ![](...) 或 <img>")
  return rewritten, uniqueRefs, mapping


def _postprocessBook(
  *,
  projectRoot: Path,
  stagingDocRoot: Path,
  sha12: str,
  humanStem: str,
  titleExtracted: Optional[str],
  finalStem: str,
) -> dict:
  vaultRoot = projectRoot / "memory-source"
  rawRoot = vaultRoot / "raw"
  assetsRoot = vaultRoot / "assets"

  _ensureInside(vaultRoot, rawRoot)
  _ensureInside(vaultRoot, assetsRoot)

  if not (vaultRoot / "CLAUDE.md").exists():
    raise ValueError("projectRoot 下缺少 memory-source/CLAUDE.md，疑似不是目标工程")

  stagingNormalizedDir = stagingDocRoot / "normalized"
  stagingMarkdownPath = stagingNormalizedDir / "document.md"
  if not stagingMarkdownPath.exists():
    raise FileNotFoundError(f"staging 缺少 normalized/document.md：{stagingMarkdownPath}")

  originalMarkdown = _readText(stagingMarkdownPath)
  originalMarkdown = _normalizeNewlines(originalMarkdown)

  rewritten, uniqueRefs, mapping = _prepareAssetsMapping(
    stagingNormalizedDir=stagingNormalizedDir,
    markdown=originalMarkdown,
    assetsBucket="books",
    finalStem=finalStem,
  )

  # 生成并保留后处理基准文本（staging 内）
  postprocessDocPath = stagingDocRoot / "postprocess" / "document.postprocessed.md"
  _writeText(postprocessDocPath, rewritten)
  postprocessedSha256 = _sha256HexFromBytes(rewritten.encode("utf-8"))

  splitMode, chunksMeta, tocRanges, strongCount, candidateCount = _splitBookMarkdown(markdown=rewritten)

  finalBooksDir = rawRoot / "04-books" / finalStem
  finalAssetsDir = assetsRoot / "raw" / "books" / finalStem
  finalManifestPath = rawRoot / "05-images" / f"{finalStem}.md"
  metaPath = finalBooksDir / "meta.json"

  # 终态已存在：hard-fail
  if finalBooksDir.exists() or finalAssetsDir.exists() or finalManifestPath.exists():
    raise FileExistsError("目标 finalStem 已存在")

  # 原子性（plan）：先写入固定 __tmp__ 路径，全部成功后再 replace 为最终路径。
  tmpBooksDir = finalBooksDir.with_name(finalBooksDir.name + ".__tmp__")
  tmpAssetsDir = finalAssetsDir.with_name(finalAssetsDir.name + ".__tmp__")
  tmpManifestPath = finalManifestPath.with_name(finalManifestPath.name + ".__tmp__")

  if tmpBooksDir.exists():
    shutil.rmtree(tmpBooksDir)
  if tmpAssetsDir.exists():
    shutil.rmtree(tmpAssetsDir)
  if tmpManifestPath.exists():
    tmpManifestPath.unlink()

  try:
    tmpAssetsDir.mkdir(parents=True, exist_ok=True)

    # 写 ch-xx.md：以 postprocessed_document 为唯一 offset 参考。
    for item in chunksMeta:
      fileName = str(item["fileName"])
      start = int(item["charStart"])
      end = int(item["charEnd"])
      content = rewritten[start:end]
      content = content.strip() + "\n"
      _writeText(tmpBooksDir / fileName, content)

    # meta.json：按 plan Step 7 记录拆分与可追溯字段
    meta = {
      "projectRoot": str(projectRoot.resolve()),
      "sourceKind": "book",
      "sha12": sha12,
      "finalStem": finalStem,
      "humanStem": humanStem,
      "titleExtracted": titleExtracted,
      "splitMode": splitMode,
      "strongCount": strongCount,
      "candidateCount": candidateCount,
      "chapterCount": len(chunksMeta),
      "tocRanges": tocRanges,
      "offsetRef": "postprocessed_document",
      "postprocessedDocumentPath": str(postprocessDocPath.resolve()),
      "postprocessedDocumentSha256": postprocessedSha256,
      "chunks": chunksMeta,
    }
    tmpBooksDir.mkdir(parents=True, exist_ok=True)
    (tmpBooksDir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # manifest-only：按 plan 模板写入（最小满足字段）
    today = datetime.utcnow().strftime("%Y-%m-%d")
    lines = [
      "---",
      f'title: "images-{finalStem}"',
      "type: source",
      "source_kind: image",
      f"sources: [raw/04-books/{finalStem}/ch-01.md]",
      f"last_updated: {today}",
      "---",
      "",
      f"# 图片清单（{finalStem}）",
      "",
    ]

    assetBinaryCount = 0
    for ref in uniqueRefs:
      normalizedRef = ref[2:] if ref.startswith("./") else ref
      if not normalizedRef.startswith("images/"):
        continue
      srcPath = stagingNormalizedDir / normalizedRef
      dstRel = mapping.get(ref) or mapping.get(normalizedRef)
      if not dstRel:
        continue
      dstName = Path(dstRel).name
      dstPath = tmpAssetsDir / dstName
      dstPath.parent.mkdir(parents=True, exist_ok=True)
      shutil.copyfile(srcPath, dstPath)
      assetBinaryCount += 1

      imgSha256 = _sha256HexFromBytes(srcPath.read_bytes())
      lines.extend(
        [
          f"- {dstName}",
          f"  - asset: {dstRel}",
          f"  - origin: normalized/{normalizedRef}",
          f"  - sha256: {imgSha256}",
        ]
      )

    manifestText = "\n".join(lines).rstrip() + "\n"
    _writeText(tmpManifestPath, manifestText)

    # 父目录确保存在
    (rawRoot / "04-books").mkdir(parents=True, exist_ok=True)
    (rawRoot / "05-images").mkdir(parents=True, exist_ok=True)
    (assetsRoot / "raw" / "books").mkdir(parents=True, exist_ok=True)

    # 最终原子 replace：尽量避免半成品（失败则回滚已 replace 的部分）
    replacedBooks = False
    replacedAssets = False
    replacedManifest = False
    try:
      os.replace(tmpBooksDir, finalBooksDir)
      replacedBooks = True
      os.replace(tmpAssetsDir, finalAssetsDir)
      replacedAssets = True
      os.replace(tmpManifestPath, finalManifestPath)
      replacedManifest = True
    except Exception:
      if replacedManifest and finalManifestPath.exists():
        try:
          finalManifestPath.unlink()
        except Exception:
          pass
      if replacedAssets and finalAssetsDir.exists():
        shutil.rmtree(finalAssetsDir, ignore_errors=True)
      if replacedBooks and finalBooksDir.exists():
        shutil.rmtree(finalBooksDir, ignore_errors=True)
      raise
  except Exception:
    # 清理临时产物，避免污染
    if tmpBooksDir.exists():
      shutil.rmtree(tmpBooksDir, ignore_errors=True)
    if tmpAssetsDir.exists():
      shutil.rmtree(tmpAssetsDir, ignore_errors=True)
    if tmpManifestPath.exists():
      try:
        tmpManifestPath.unlink()
      except Exception:
        pass
    raise

  rawDir = finalBooksDir
  assetsDir = finalAssetsDir
  writtenFiles = {
    "rawMarkdownCount": len(list(finalBooksDir.glob("ch-*.md"))),
    "assetBinaryCount": len(list(finalAssetsDir.glob("*"))),
    "manifestCount": 1,
    "metaCount": 1,
  }

  return {
    "projectRoot": str(projectRoot.resolve()),
    "sourceKind": "book",
    "finalStem": finalStem,
    "stagingDocRoot": str(stagingDocRoot.resolve()),
    "rawDir": str(rawDir.resolve()),
    "assetsDir": str(assetsDir.resolve()),
    "metaPath": str(metaPath.resolve()),
    "manifestPath": str(finalManifestPath.resolve()),
    "writtenFiles": writtenFiles,
  }


def _postprocessNonBook(
  *,
  projectRoot: Path,
  stagingDocRoot: Path,
  sourceKind: str,
  sha12: str,
  humanStem: str,
  titleExtracted: Optional[str],
  finalStem: str,
) -> dict:
  vaultRoot = projectRoot / "memory-source"
  rawRoot = vaultRoot / "raw"
  assetsRoot = vaultRoot / "assets"

  rawSubdir, assetsBucket = _getBuckets(sourceKind)
  bucketRoot = rawRoot / rawSubdir

  stagingNormalizedDir = stagingDocRoot / "normalized"
  stagingMarkdownPath = stagingNormalizedDir / "document.md"
  if not stagingMarkdownPath.exists():
    raise FileNotFoundError(f"staging 缺少 normalized/document.md：{stagingMarkdownPath}")

  originalMarkdown = _normalizeNewlines(_readText(stagingMarkdownPath))
  rewritten, uniqueRefs, mapping = _prepareAssetsMapping(
    stagingNormalizedDir=stagingNormalizedDir,
    markdown=originalMarkdown,
    assetsBucket=assetsBucket,
    finalStem=finalStem,
  )

  postprocessDocPath = stagingDocRoot / "postprocess" / "document.postprocessed.md"
  _writeText(postprocessDocPath, rewritten)
  postprocessedSha256 = _sha256HexFromBytes(rewritten.encode("utf-8"))

  finalRawDir = bucketRoot / finalStem
  finalAssetsDir = assetsRoot / "raw" / assetsBucket / finalStem
  finalManifestPath = rawRoot / "05-images" / f"{finalStem}.md"
  metaPath = finalRawDir / "meta.json"
  documentPath = finalRawDir / "document.md"

  if finalRawDir.exists() or finalAssetsDir.exists() or finalManifestPath.exists():
    raise FileExistsError("目标 finalStem 已存在")

  tmpRawDir = finalRawDir.with_name(finalRawDir.name + ".__tmp__")
  tmpAssetsDir = finalAssetsDir.with_name(finalAssetsDir.name + ".__tmp__")
  tmpManifestPath = finalManifestPath.with_name(finalManifestPath.name + ".__tmp__")

  if tmpRawDir.exists():
    shutil.rmtree(tmpRawDir)
  if tmpAssetsDir.exists():
    shutil.rmtree(tmpAssetsDir)
  if tmpManifestPath.exists():
    tmpManifestPath.unlink()

  try:
    tmpAssetsDir.mkdir(parents=True, exist_ok=True)

    _writeText(tmpRawDir / "document.md", rewritten)

    meta = {
      "projectRoot": str(projectRoot.resolve()),
      "sourceKind": sourceKind,
      "sha12": sha12,
      "finalStem": finalStem,
      "humanStem": humanStem,
      "titleExtracted": titleExtracted,
      "offsetRef": "postprocessed_document",
      "postprocessedDocumentPath": str(postprocessDocPath.resolve()),
      "postprocessedDocumentSha256": postprocessedSha256,
    }
    (tmpRawDir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    today = datetime.utcnow().strftime("%Y-%m-%d")
    lines = [
      "---",
      f'title: "images-{finalStem}"',
      "type: source",
      "source_kind: image",
      f"sources: [raw/{rawSubdir}/{finalStem}/document.md]",
      f"last_updated: {today}",
      "---",
      "",
      f"# 图片清单（{finalStem}）",
      "",
    ]

    for ref in uniqueRefs:
      normalizedRef = ref[2:] if ref.startswith("./") else ref
      srcPath = stagingNormalizedDir / normalizedRef
      dstRel = mapping.get(ref) or mapping.get(normalizedRef)
      if not dstRel:
        continue
      dstName = Path(dstRel).name
      dstPath = tmpAssetsDir / dstName
      dstPath.parent.mkdir(parents=True, exist_ok=True)
      shutil.copyfile(srcPath, dstPath)

      imgSha256 = _sha256HexFromBytes(srcPath.read_bytes())
      lines.extend(
        [
          f"- {dstName}",
          f"  - asset: {dstRel}",
          f"  - origin: normalized/{normalizedRef}",
          f"  - sha256: {imgSha256}",
        ]
      )

    _writeText(tmpManifestPath, "\n".join(lines).rstrip() + "\n")

    bucketRoot.mkdir(parents=True, exist_ok=True)
    (rawRoot / "05-images").mkdir(parents=True, exist_ok=True)
    (assetsRoot / "raw" / assetsBucket).mkdir(parents=True, exist_ok=True)

    replacedRaw = False
    replacedAssets = False
    replacedManifest = False
    try:
      os.replace(tmpRawDir, finalRawDir)
      replacedRaw = True
      os.replace(tmpAssetsDir, finalAssetsDir)
      replacedAssets = True
      os.replace(tmpManifestPath, finalManifestPath)
      replacedManifest = True
    except Exception:
      if replacedManifest and finalManifestPath.exists():
        try:
          finalManifestPath.unlink()
        except Exception:
          pass
      if replacedAssets and finalAssetsDir.exists():
        shutil.rmtree(finalAssetsDir, ignore_errors=True)
      if replacedRaw and finalRawDir.exists():
        shutil.rmtree(finalRawDir, ignore_errors=True)
      raise
  except Exception:
    if tmpRawDir.exists():
      shutil.rmtree(tmpRawDir, ignore_errors=True)
    if tmpAssetsDir.exists():
      shutil.rmtree(tmpAssetsDir, ignore_errors=True)
    if tmpManifestPath.exists():
      try:
        tmpManifestPath.unlink()
      except Exception:
        pass
    raise

  writtenFiles = {
    "rawMarkdownCount": 1,
    "assetBinaryCount": len(list(finalAssetsDir.glob("*"))),
    "manifestCount": 1,
    "metaCount": 1,
  }

  return {
    "projectRoot": str(projectRoot.resolve()),
    "sourceKind": sourceKind,
    "finalStem": finalStem,
    "stagingDocRoot": str(stagingDocRoot.resolve()),
    "rawDir": str(finalRawDir.resolve()),
    "assetsDir": str(finalAssetsDir.resolve()),
    "metaPath": str(metaPath.resolve()),
    "manifestPath": str(finalManifestPath.resolve()),
    "writtenFiles": writtenFiles,
  }


def _parsePostprocessArgs(argv: List[str]) -> argparse.Namespace:
  parser = argparse.ArgumentParser(prog="document-parser postprocess")
  parser.add_argument("--project-root", dest="projectRoot", required=True)
  parser.add_argument("--source-kind", dest="sourceKind", required=True, choices=_SOURCE_KIND_CHOICES)
  parser.add_argument(
    "--sha12",
    dest="sha12",
    default=None,
    help="仅在 --staging-doc-root 模式下可选：覆盖 sha12（12 位小写十六进制）",
  )

  group = parser.add_mutually_exclusive_group(required=True)
  group.add_argument("--input", dest="input", default=None)
  group.add_argument("--staging-doc-root", dest="stagingDocRoot", default=None)

  return parser.parse_args(argv)


def _runPostprocess(argv: List[str]) -> int:
  try:
    args = _parsePostprocessArgs(argv)
  except SystemExit as e:
    code = e.code
    if isinstance(code, int):
      return code
    return 2

  projectRoot = Path(args.projectRoot)
  if not projectRoot.exists():
    print("ERROR: projectRoot 不存在", file=sys.stderr)
    return 3

  vaultRoot = projectRoot / "memory-source"
  if not vaultRoot.exists():
    print("ERROR: projectRoot 下缺少 memory-source/", file=sys.stderr)
    return 3
  if not (vaultRoot / "CLAUDE.md").exists():
    print("ERROR: memory-source/CLAUDE.md 不存在", file=sys.stderr)
    return 3
  rawRoot = vaultRoot / "raw"
  assetsRoot = vaultRoot / "assets"
  if not rawRoot.exists() or not assetsRoot.exists():
    print("ERROR: memory-source/raw 或 memory-source/assets 不存在", file=sys.stderr)
    return 3

  sha12: Optional[str] = None

  if args.stagingDocRoot:
    stagingDocRoot = Path(args.stagingDocRoot)
  else:
    # input 模式：固定 staging 根目录
    stagingRoot = projectRoot / ".cache" / "document-parser"
    inputPath = Path(args.input)
    if not inputPath.exists():
      print("ERROR: input 文件不存在", file=sys.stderr)
      return 3
    sha12 = _sha12FromFileBytes(inputPath)
    stagingDocRoot = stagingRoot / "document_parser_output" / sha12

  if not stagingDocRoot.exists():
    print("ERROR: stagingDocRoot 不存在", file=sys.stderr)
    return 3

  # 计算 sha12（staging 模式可覆盖）
  if args.stagingDocRoot:
    if args.sha12 is not None:
      sha12 = str(args.sha12).strip().lower()
      if not _isHexSha12(sha12):
        print("ERROR: --sha12 必须是 12 位小写十六进制", file=sys.stderr)
        return 2
    else:
      try:
        sha12 = _sha12FromStagingInputs(stagingDocRoot)
      except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 3

  if sha12 is None:
    print("ERROR: sha12 计算失败", file=sys.stderr)
    return 7

  # 提取 humanStem
  normalizedDocPath = stagingDocRoot / "normalized" / "document.md"
  try:
    normalizedMarkdown = _readText(normalizedDocPath)
  except Exception as e:
    print(f"ERROR: {e}", file=sys.stderr)
    return 3
  title = _extractTitleFromMarkdownFirstLine(_normalizeNewlines(normalizedMarkdown))

  sourceFileStem = None
  if args.input:
    sourceFileStem = Path(args.input).stem
  else:
    sourceFileStem = stagingDocRoot.name

  rawSubdir, _assetsBucket = _getBuckets(args.sourceKind)
  bucketDir = rawRoot / rawSubdir
  finalStem, humanStem, titleExtracted = _resolveFinalStem(
    bucketDir=bucketDir,
    sha12=sha12,
    title=title,
    sourceFileStem=sourceFileStem,
  )

  try:
    if args.sourceKind == "book":
      data = _postprocessBook(
        projectRoot=projectRoot,
        stagingDocRoot=stagingDocRoot,
        sha12=sha12,
        humanStem=humanStem,
        titleExtracted=titleExtracted,
        finalStem=finalStem,
      )
    else:
      data = _postprocessNonBook(
        projectRoot=projectRoot,
        stagingDocRoot=stagingDocRoot,
        sourceKind=args.sourceKind,
        sha12=sha12,
        humanStem=humanStem,
        titleExtracted=titleExtracted,
        finalStem=finalStem,
      )
  except FileExistsError:
    print("ERROR: 目标已存在", file=sys.stderr)
    return 6
  except (ValueError, FileNotFoundError) as e:
    print(f"ERROR: {e}", file=sys.stderr)
    return 7
  except Exception as e:
    print(f"ERROR: {e}", file=sys.stderr)
    return 7

  # stdout 合同：只输出一行 JSON
  print(json.dumps(data, ensure_ascii=False))
  return 0


def _runValidate(argv: List[str]) -> int:
  parser = argparse.ArgumentParser(prog="document-parser validate")
  parser.add_argument("--project-root", dest="projectRoot", required=True)
  try:
    args = parser.parse_args(argv)
  except SystemExit as e:
    code = e.code
    if isinstance(code, int):
      return code
    return 2

  projectRoot = Path(args.projectRoot)
  vaultRoot = projectRoot / "memory-source"

  def _emitError(code: str, *, message: str, path: Path, file: Optional[Path] = None, ref: Optional[str] = None) -> None:
    fields: list[tuple[str, str]] = [("message", message), ("path", str(path))]
    if file is not None:
      fields.append(("file", str(file)))
    if ref is not None:
      fields.append(("ref", ref))

    def _escape(value: str) -> str:
      return value.replace("\\", "\\\\").replace('"', "\\\"")

    kv = " ".join(f"{k}=\"{_escape(v)}\"" for k, v in fields)
    print(f"ERROR_CODE:{code} {kv}", file=sys.stderr)

  def _isForbiddenRefText(text: str) -> bool:
    lowered = text.strip().lower()
    if "\\" in text:
      return True
    if lowered.startswith("/"):
      return True
    if lowered.startswith("file://"):
      return True
    if lowered.startswith("http://") or lowered.startswith("https://"):
      return True
    if ".." in text:
      return True
    return False

  def _iterMarkdownFiles(rawRoot: Path) -> list[Path]:
    candidates = sorted(p for p in rawRoot.rglob("*.md") if p.is_file())
    imagesDir = (rawRoot / "05-images").resolve()
    result: list[Path] = []
    for path in candidates:
      try:
        if path.resolve().is_relative_to(imagesDir):
          continue
      except AttributeError:
        # py<3.9 兼容：本仓库运行环境为 3.12，保守留着。
        try:
          path.resolve().relative_to(imagesDir)
          continue
        except Exception:
          pass
      result.append(path)
    return result

  if not vaultRoot.exists():
    _emitError("V003", message="projectRoot 下缺少 memory-source/", path=vaultRoot)
    print("SUMMARY ok=0 errors=1", file=sys.stderr)
    return 3
  if not (vaultRoot / "CLAUDE.md").exists():
    _emitError("V003", message="memory-source/CLAUDE.md 不存在", path=(vaultRoot / "CLAUDE.md"))
    print("SUMMARY ok=0 errors=1", file=sys.stderr)
    return 3

  rawRoot = vaultRoot / "raw"
  assetsRoot = vaultRoot / "assets"
  if not rawRoot.exists() or not assetsRoot.exists():
    missing = rawRoot if not rawRoot.exists() else assetsRoot
    _emitError("V003", message="memory-source/raw 或 memory-source/assets 不存在", path=missing)
    print("SUMMARY ok=0 errors=1", file=sys.stderr)
    return 3

  errors = 0
  hasV004 = False
  hasV005 = False

  # V004：扫描 raw 下禁止的二进制/过程工件
  forbiddenFileNames = {".ds_store", "thumbs.db"}
  forbiddenSuffixes = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".pdf",
    ".zip",
    ".jsonl",
    ".pyc",
    ".pyo",
    ".tmp",
    ".part",
    ".crdownload",
  }

  for path in sorted(rawRoot.rglob("*")):
    if path.is_dir() and path.name == "__pycache__":
      errors += 1
      hasV004 = True
      _emitError("V004", message="raw/ 下存在禁止的过程目录", path=path)
      continue
    if not path.is_file():
      continue
    if path.name.lower() in forbiddenFileNames or path.suffix.lower() in forbiddenSuffixes:
      errors += 1
      hasV004 = True
      _emitError("V004", message="raw/ 下存在禁止的二进制或过程工件", path=path)

  # raw/05-images 仅允许 *.md
  imagesDir = rawRoot / "05-images"
  if imagesDir.exists():
    for path in sorted(imagesDir.rglob("*")):
      if path.is_dir():
        continue
      if not path.is_file():
        continue
      if path.suffix.lower() != ".md":
        errors += 1
        hasV004 = True
        _emitError("V004", message="raw/05-images/ 仅允许 .md 文件", path=path)

  # V005：终态 raw markdown 校验
  for mdPath in _iterMarkdownFiles(rawRoot):
    try:
      markdown = _readText(mdPath)
    except Exception as e:
      errors += 1
      _emitError("V003", message=f"读取 markdown 失败：{e}", path=mdPath)
      continue

    mdImageMatch = _MD_IMAGE_RE.search(markdown)
    if mdImageMatch:
      errors += 1
      hasV005 = True
      _emitError(
        "V005",
        message="终态 raw 不允许出现标准 Markdown 图片 ![](...)",
        path=mdPath,
        file=mdPath,
        ref=mdImageMatch.group(0),
      )
    htmlImageMatch = _HTML_IMAGE_RE.search(markdown)
    if htmlImageMatch:
      errors += 1
      hasV005 = True
      _emitError(
        "V005",
        message="终态 raw 不允许出现 HTML <img>",
        path=mdPath,
        file=mdPath,
        ref=htmlImageMatch.group(0),
      )

    for match in _OBSIDIAN_EMBED_RE.finditer(markdown):
      target = match.group(1).strip()
      if _isForbiddenRefText(target):
        errors += 1
        hasV005 = True
        _emitError(
          "V005",
          message="终态 raw embed 引用包含非法路径",
          path=mdPath,
          file=mdPath,
          ref=target,
        )
        continue

      allowed = _ALLOWED_EMBED_TARGET_RE.fullmatch(target)
      if not allowed:
        errors += 1
        hasV005 = True
        _emitError(
          "V005",
          message="终态 raw 仅允许引用 assets/raw/<bucket>/<finalStem>/<fileName>",
          path=mdPath,
          file=mdPath,
          ref=target,
        )
        continue

      resolved = (vaultRoot / target).resolve()
      try:
        _ensureInside(vaultRoot, resolved)
      except Exception:
        errors += 1
        hasV005 = True
        _emitError(
          "V003",
          message="embed 引用越界（不在 memory-source 内）",
          path=mdPath,
          file=mdPath,
          ref=target,
        )
        continue

      if not resolved.exists():
        errors += 1
        hasV005 = True
        _emitError(
          "V005",
          message="embed 引用指向不存在的目标",
          path=mdPath,
          file=mdPath,
          ref=target,
        )

  ok = 1 if errors == 0 else 0
  print(f"SUMMARY ok={ok} errors={errors}", file=sys.stderr)

  if errors == 0:
    return 0
  if hasV004:
    return 4
  if hasV005:
    return 5
  return 3


def _parseParseArgs(argv: List[str]) -> argparse.Namespace:
  parser = argparse.ArgumentParser(prog="document-parser parse")
  parser.add_argument("--project-root", dest="projectRoot", required=False)
  parser.add_argument("--input", dest="input", required=False)
  return parser.parse_args(argv)


def _parseDryRunArgs(argv: List[str]) -> argparse.Namespace:
  parser = argparse.ArgumentParser(prog="document-parser dry-run")
  parser.add_argument("--project-root", dest="projectRoot", required=False)
  return parser.parse_args(argv)


def _validateProjectRootRequired(projectRootRaw: Optional[str]) -> Path:
  if projectRootRaw is None or not str(projectRootRaw).strip():
    raise ValueError("必须提供 --project-root")

  projectRoot = Path(str(projectRootRaw)).expanduser()
  if not projectRoot.exists() or not projectRoot.is_dir():
    raise FileNotFoundError("projectRoot 不存在")
  return projectRoot.resolve()


def _getStagingRoot(*, projectRoot: Path) -> Path:
  return projectRoot / ".cache" / "document-parser"


def _isPathInside(*, baseDir: Path, candidate: Path) -> bool:
  baseResolved = baseDir.resolve()
  candidateResolved = candidate.resolve()
  try:
    candidateResolved.relative_to(baseResolved)
  except Exception:
    return False
  return True


def _runParse(argv: List[str]) -> int:
  try:
    args = _parseParseArgs(argv)
  except SystemExit as e:
    code = e.code
    if isinstance(code, int):
      return code
    return 2

  try:
    projectRoot = _validateProjectRootRequired(args.projectRoot)
  except ValueError as e:
    print(f"ERROR: {e}", file=sys.stderr)
    return 2
  except FileNotFoundError as e:
    print(f"ERROR: {e}", file=sys.stderr)
    return 3

  inputValue = (str(args.input).strip() if args.input is not None else "")
  if not inputValue:
    print("ERROR: 必须提供 --input", file=sys.stderr)
    return 2

  vaultRoot = projectRoot / "memory-source"
  stagingRoot = _getStagingRoot(projectRoot=projectRoot)
  if vaultRoot.exists() and _isPathInside(baseDir=vaultRoot, candidate=stagingRoot):
    print("ERROR: stagingRoot 不允许位于 memory-source/ 内", file=sys.stderr)
    return 3

  try:
    results = _orchestrator.parseMany(sources=[inputValue], outputDir=stagingRoot)
  except Exception as e:
    print(f"ERROR: {e}", file=sys.stderr)
    return 1

  for result in results:
    print(result.paths.normalizedMarkdownPath)
  return 0


def _runDryRun(argv: List[str]) -> int:
  try:
    args = _parseDryRunArgs(argv)
  except SystemExit as e:
    code = e.code
    if isinstance(code, int):
      return code
    return 2

  try:
    projectRoot = _validateProjectRootRequired(args.projectRoot)
  except ValueError as e:
    print(f"ERROR: {e}", file=sys.stderr)
    return 2
  except FileNotFoundError as e:
    print(f"ERROR: {e}", file=sys.stderr)
    return 3

  vaultRoot = projectRoot / "memory-source"
  rawRoot = vaultRoot / "raw"
  assetsRoot = vaultRoot / "assets"
  manifestRoot = rawRoot / "05-images"
  stagingRoot = _getStagingRoot(projectRoot=projectRoot)

  # 路径校验：必须在目标工程下执行，且 staging 不得进入 vault 内。
  if not vaultRoot.exists():
    print("ERROR: projectRoot 下缺少 memory-source/", file=sys.stderr)
    return 3
  if not (vaultRoot / "CLAUDE.md").exists():
    print("ERROR: memory-source/CLAUDE.md 不存在", file=sys.stderr)
    return 3
  if not rawRoot.exists() or not assetsRoot.exists():
    print("ERROR: memory-source/raw 或 memory-source/assets 不存在", file=sys.stderr)
    return 3
  if _isPathInside(baseDir=vaultRoot, candidate=stagingRoot):
    print("ERROR: stagingRoot 不允许位于 memory-source/ 内", file=sys.stderr)
    return 3

  data = {
    "projectRoot": str(projectRoot),
    "vaultRoot": str(vaultRoot.resolve()),
    "stagingRoot": str(stagingRoot.resolve()),
    "rawRoot": str(rawRoot.resolve()),
    "assetsRoot": str(assetsRoot.resolve()),
    "manifestRoot": str(manifestRoot.resolve()),
    "policy": {
      "projectRootRequired": True,
      "stagingOutsideVault": True,
      "rawNoBinaries": True,
      "imageLinkStyle": "obsidian-embed",
    },
  }

  # stdout 合同：只输出一行 JSON
  print(json.dumps(data, ensure_ascii=False))
  return 0


def main(argv: Optional[List[str]] = None) -> int:
  argvList = list(argv) if argv is not None else sys.argv[1:]
  if argvList[:1] == ["parse"]:
    return _runParse(argvList[1:])
  if argvList[:1] == ["dry-run"]:
    return _runDryRun(argvList[1:])
  if argvList[:1] == ["postprocess"]:
    return _runPostprocess(argvList[1:])
  if argvList[:1] == ["validate"]:
    return _runValidate(argvList[1:])

  # 兼容旧接口：未指定子命令时按 parseMany 处理。
  return _parseLegacyParseMany(argvList)


if __name__ == "__main__":
  raise SystemExit(main())
