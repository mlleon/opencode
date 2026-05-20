import os
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory
from unittest import TestCase, mock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "transcribe.py"


def load_transcribe_module():
    spec = importlib.util.spec_from_file_location("transcribe", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_result(audio_processed: float, transcript: str, words=None):
    if words is None:
        words = []
    return SimpleNamespace(
        audio_processed=audio_processed,
        alternatives=[SimpleNamespace(transcript=transcript, words=words)],
    )


class TranscribeTests(TestCase):
    def test_default_window_and_overlap_constants(self):
        module = load_transcribe_module()

        self.assertEqual(module.WINDOW_DURATION_SEC, 10.0)
        self.assertEqual(module.WINDOW_OVERLAP_SEC, 2.0)

    def test_trim_overlapping_prefix_removes_overlap(self):
        module = load_transcribe_module()

        trimmed = module.trim_overlapping_prefix(
            "你好世界今天",  # suffix: 世界今天
            "世界今天吃饭",  # prefix overlap: 世界今天
            max_overlap=10,
        )
        self.assertEqual(trimmed, "吃饭")

        trimmed_with_spaces = module.trim_overlapping_prefix(
            "你好 世界 今天",
            "世界 今天 吃饭",
            max_overlap=10,
        )
        self.assertEqual(trimmed_with_spaces, "吃饭")

    def test_build_request_ranges_uses_overlap(self):
        module = load_transcribe_module()

        self.assertEqual(
            module.build_request_ranges(30.0, window_sec=15.0, overlap_sec=1.0),
            [(0.0, 15.0), (14.0, 29.0), (28.0, 30.0)],
        )

        self.assertEqual(
            module.build_request_ranges(30.0, window_sec=10.0, overlap_sec=2.0),
            [(0.0, 10.0), (8.0, 18.0), (16.0, 26.0), (24.0, 30.0)],
        )

        self.assertEqual(
            module.build_request_ranges(15.0, window_sec=15.0, overlap_sec=1.0),
            [(0.0, 15.0)],
        )

        self.assertEqual(
            module.build_request_ranges(14.0, window_sec=15.0, overlap_sec=1.0),
            [(0.0, 14.0)],
        )

    def test_build_chunk_ranges_limits_to_audio_duration(self):
        module = load_transcribe_module()

        self.assertEqual(
            module.build_chunk_ranges(266.2, module.CHUNK_DURATION_SEC),
            [(0.0, 266.2)],
        )
        self.assertEqual(
            module.build_chunk_ranges(601.0, module.CHUNK_DURATION_SEC),
            [(0.0, 300.0), (300.0, 600.0), (600.0, 601.0)],
        )

    def test_split_wav_uses_duration_bounded_ranges(self):
        module = load_transcribe_module()

        calls = []

        def fake_run(cmd, capture_output, text):
            calls.append(cmd)
            out_path = Path(cmd[-2])
            out_path.write_bytes(b"RIFF" + b"\x00" * 2048)
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        with mock.patch.object(module, "get_audio_info", return_value={"duration": 601.0, "size": 1}):
            with mock.patch.object(module.subprocess, "run", side_effect=fake_run):
                with TemporaryDirectory(dir=PROJECT_ROOT) as tmp_dir_name:
                    tmp_dir = Path(tmp_dir_name)
                    wav_path = tmp_dir / "input.wav"
                    wav_path.write_bytes(b"dummy")
                    chunks = module.split_wav(wav_path, tmp_dir)

        self.assertEqual(len(chunks), 3)
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[0][calls[0].index("-t") + 1], "300")
        self.assertEqual(calls[1][calls[1].index("-t") + 1], "300")
        self.assertEqual(calls[2][calls[2].index("-t") + 1], "1")

    def test_build_segments_uses_audio_processed_when_words_missing(self):
        module = load_transcribe_module()

        results = [
            make_result(30.0, "第一段文本"),
            make_result(60.0, "第二段文本"),
            make_result(90.0, "第三段文本"),
        ]

        segments = module.build_segments_from_results(results)

        self.assertEqual(
            segments,
            [
                {"start": 0.0, "end": 30.0, "text": "第一段文本"},
                {"start": 30.0, "end": 60.0, "text": "第二段文本"},
                {"start": 60.0, "end": 90.0, "text": "第三段文本"},
            ],
        )

    def test_transcribe_with_nim_uses_fixed_windows(self):
        module = load_transcribe_module()

        with TemporaryDirectory(dir=PROJECT_ROOT) as tmp_dir_name:
            tmp_dir = Path(tmp_dir_name)
            video_path = tmp_dir / "sample.mp4"
            audio_path = video_path.with_suffix(".wav")
            video_path.write_bytes(b"video")
            audio_path.write_bytes(b"audio")

            request_map = {
                (0.0, 10.0): {"results": [make_result(10.0, "第一段文本")]},
                (8.0, 18.0): {"results": [make_result(10.0, "第二段文本")]},
                (16.0, 26.0): {"results": [make_result(10.0, "第三段文本")]},
                (24.0, 31.0): {"results": [make_result(7.0, "第四段文本")]},
            }

            def fake_transcribe_request(server, metadata, audio_path_arg, language, request_start, request_end):
                self.assertEqual(audio_path_arg, audio_path)
                return request_map[(request_start, request_end)]

            with mock.patch.dict(os.environ, {"NIM_API_KEY": "nvapi-test"}, clear=False):
                with mock.patch.object(module, "get_audio_info", return_value={"duration": 31.0, "size": 1}):
                    with mock.patch.object(module, "transcribe_request", side_effect=fake_transcribe_request):
                        result = module.transcribe_with_nim(video_path, "zh-CN")

        self.assertEqual(
            result["segments"],
            [
                {"start": 0.0, "end": 10.0, "text": "第一段文本"},
                {"start": 8.0, "end": 18.0, "text": "第二段文本"},
                {"start": 16.0, "end": 26.0, "text": "第三段文本"},
                {"start": 24.0, "end": 31.0, "text": "第四段文本"},
            ],
        )

    def test_transcribe_with_nim_trims_overlap_between_windows(self):
        module = load_transcribe_module()

        with TemporaryDirectory(dir=PROJECT_ROOT) as tmp_dir_name:
            tmp_dir = Path(tmp_dir_name)
            video_path = tmp_dir / "sample.mp4"
            audio_path = video_path.with_suffix(".wav")
            video_path.write_bytes(b"video")
            audio_path.write_bytes(b"audio")

            request_map = {
                (0.0, 10.0): {"results": [make_result(10.0, "甲乙丙丁")]},
                (8.0, 18.0): {"results": [make_result(10.0, "丁戊己庚")]},
                (16.0, 26.0): {"results": [make_result(10.0, "庚辛壬癸")]},
                (24.0, 31.0): {"results": [make_result(7.0, "癸子丑寅")]},
            }

            def fake_transcribe_request(server, metadata, audio_path_arg, language, request_start, request_end):
                self.assertEqual(audio_path_arg, audio_path)
                return request_map[(request_start, request_end)]

            with mock.patch.dict(os.environ, {"NIM_API_KEY": "nvapi-test"}, clear=False):
                with mock.patch.object(module, "get_audio_info", return_value={"duration": 31.0, "size": 1}):
                    with mock.patch.object(module, "transcribe_request", side_effect=fake_transcribe_request):
                        result = module.transcribe_with_nim(video_path, "zh-CN")

        self.assertEqual(
            result["segments"],
            [
                {"start": 0.0, "end": 10.0, "text": "甲乙丙丁"},
                {"start": 8.0, "end": 18.0, "text": "戊己庚"},
                {"start": 16.0, "end": 26.0, "text": "辛壬癸"},
                {"start": 24.0, "end": 31.0, "text": "子丑寅"},
            ],
        )

    def test_transcribe_with_nim_does_not_reset_overlap_state_when_trimmed_empty(self):
        module = load_transcribe_module()

        with TemporaryDirectory(dir=PROJECT_ROOT) as tmp_dir_name:
            tmp_dir = Path(tmp_dir_name)
            video_path = tmp_dir / "sample.mp4"
            audio_path = video_path.with_suffix(".wav")
            video_path.write_bytes(b"video")
            audio_path.write_bytes(b"audio")

            request_map = {
                (0.0, 10.0): {"results": [make_result(10.0, "甲乙丙丁")]},
                # 完全重复，trim 后为空
                (8.0, 18.0): {"results": [make_result(10.0, "甲乙丙丁")]},
                # 下一段仍应基于上一段（甲乙丙丁）去重
                (16.0, 20.0): {"results": [make_result(4.0, "丙丁戊己")]},
            }

            def fake_transcribe_request(server, metadata, audio_path_arg, language, request_start, request_end):
                self.assertEqual(audio_path_arg, audio_path)
                return request_map[(request_start, request_end)]

            with mock.patch.dict(os.environ, {"NIM_API_KEY": "nvapi-test"}, clear=False):
                with mock.patch.object(module, "get_audio_info", return_value={"duration": 20.0, "size": 1}):
                    with mock.patch.object(module, "transcribe_request", side_effect=fake_transcribe_request):
                        result = module.transcribe_with_nim(video_path, "zh-CN")

        self.assertEqual(
            result["segments"],
            [
                {"start": 0.0, "end": 10.0, "text": "甲乙丙丁"},
                {"start": 16.0, "end": 20.0, "text": "戊己"},
            ],
        )

    def test_transcribe_with_nim_does_not_delete_existing_wav(self):
        module = load_transcribe_module()

        with TemporaryDirectory(dir=PROJECT_ROOT) as tmp_dir_name:
            tmp_dir = Path(tmp_dir_name)
            video_path = tmp_dir / "sample.mp4"
            audio_path = video_path.with_suffix(".wav")
            video_path.write_bytes(b"video")
            audio_path.write_bytes(b"preexisting-audio")

            request_map = {
                (0.0, 10.0): {"results": [make_result(10.0, "第一段文本")]},
            }

            def fake_transcribe_request(server, metadata, audio_path_arg, language, request_start, request_end):
                self.assertEqual(audio_path_arg, audio_path)
                return request_map[(request_start, request_end)]

            with mock.patch.dict(os.environ, {"NIM_API_KEY": "nvapi-test"}, clear=False):
                with mock.patch.object(module, "get_audio_info", return_value={"duration": 10.0, "size": 1}):
                    with mock.patch.object(module, "transcribe_request", side_effect=fake_transcribe_request):
                        module.transcribe_with_nim(video_path, "zh-CN")

            self.assertTrue(audio_path.exists())

    def test_transcribe_with_nim_calls_progress_callback_incrementally(self):
        module = load_transcribe_module()

        with TemporaryDirectory(dir=PROJECT_ROOT) as tmp_dir_name:
            tmp_dir = Path(tmp_dir_name)
            video_path = tmp_dir / "sample.mp4"
            audio_path = video_path.with_suffix(".wav")
            video_path.write_bytes(b"video")
            audio_path.write_bytes(b"audio")

            request_map = {
                (0.0, 10.0): {"results": [make_result(10.0, "第一段")]},
                (8.0, 18.0): {"results": [make_result(10.0, "第二段")]},
            }

            def fake_transcribe_request(server, metadata, audio_path_arg, language, request_start, request_end):
                self.assertEqual(audio_path_arg, audio_path)
                return request_map[(request_start, request_end)]

            progress_calls: list[int] = []

            def progress_callback(segments, window_index, total_windows):
                self.assertIsInstance(segments, list)
                self.assertGreaterEqual(window_index, 1)
                self.assertEqual(total_windows, 2)
                progress_calls.append(len(segments))

            with mock.patch.dict(os.environ, {"NIM_API_KEY": "nvapi-test"}, clear=False):
                with mock.patch.object(module, "get_audio_info", return_value={"duration": 18.0, "size": 1}):
                    with mock.patch.object(module, "transcribe_request", side_effect=fake_transcribe_request):
                        result = module.transcribe_with_nim(video_path, "zh-CN", progress_callback=progress_callback)

        self.assertEqual(progress_calls, [1, 2])
        self.assertEqual(len(result["segments"]), 2)

    def test_transcribe_to_files_writes_txt_and_json(self):
        module = load_transcribe_module()

        with TemporaryDirectory(dir=PROJECT_ROOT) as tmp_dir_name:
            tmp_dir = Path(tmp_dir_name)
            video_path = tmp_dir / "sample.mp4"
            video_path.write_bytes(b"video")

            fake_result = {
                "segments": [
                    {"start": 0.0, "end": 10.0, "text": "第一段"},
                    {"start": 8.0, "end": 18.0, "text": "第二段"},
                ]
            }

            with mock.patch.object(module, "transcribe_with_nim", return_value=fake_result):
                outputs = module.transcribe_to_files(video_path, "zh-CN")

            txt_content = outputs["txt"].read_text(encoding="utf-8")
            json_content = outputs["json"].read_text(encoding="utf-8")

            self.assertTrue(outputs["txt"].exists())
            self.assertTrue(outputs["json"].exists())
            self.assertEqual(outputs["txt"].parent.name, video_path.stem)

            self.assertIn("00:00 第一段", txt_content)
            self.assertIn("00:08 第二段", txt_content)
            self.assertIn("\"segments\"", json_content)

    def test_transcribe_to_files_writes_partial_during_asr(self):
        module = load_transcribe_module()

        with TemporaryDirectory(dir=PROJECT_ROOT) as tmp_dir_name:
            tmp_dir = Path(tmp_dir_name)
            video_path = tmp_dir / "sample.mp4"
            video_path.write_bytes(b"video")

            def fake_transcribe_with_nim(_video_path: Path, _language: str, progress_callback=None, **_kwargs):
                if progress_callback is not None:
                    progress_callback([
                        {"start": 0.0, "end": 10.0, "text": "第一段"},
                    ], 1, 2)
                    progress_callback([
                        {"start": 0.0, "end": 10.0, "text": "第一段"},
                        {"start": 8.0, "end": 18.0, "text": "第二段"},
                    ], 2, 2)
                return {
                    "segments": [
                        {"start": 0.0, "end": 10.0, "text": "第一段"},
                        {"start": 8.0, "end": 18.0, "text": "第二段"},
                    ]
                }

            with mock.patch.object(module, "list_subtitle_streams", return_value=[]):
                with mock.patch.object(module, "transcribe_with_nim", side_effect=fake_transcribe_with_nim):
                    outputs = module.transcribe_to_files(video_path, "zh-CN")

            partial_json = outputs["json"].with_suffix(".json.partial")
            partial_txt = outputs["txt"].with_suffix(".txt.partial")
            self.assertFalse(partial_json.exists())
            self.assertFalse(partial_txt.exists())
            self.assertTrue(outputs["json"].exists())
            self.assertTrue(outputs["txt"].exists())

    def test_transcribe_to_files_resumes_from_partial(self):
        module = load_transcribe_module()

        with TemporaryDirectory(dir=PROJECT_ROOT) as tmp_dir_name:
            tmp_dir = Path(tmp_dir_name)
            video_path = tmp_dir / "sample.mp4"
            video_path.write_bytes(b"video")
            # 预先放一个 wav，避免 transcribe_with_nim 触发 ffmpeg 提取音频
            video_path.with_suffix(".wav").write_bytes(b"audio")

            output_dir = tmp_dir / "sample"
            output_dir.mkdir(exist_ok=True)
            partial_json = output_dir / "sample.json.partial"
            partial_txt = output_dir / "sample.txt.partial"

            # 模拟：已完成第一个窗口
            partial_payload = {
                "source": str(video_path),
                "output_dir": str(output_dir),
                "language": "zh-CN",
                "source_type": "asr:nim",
                "window_duration_sec": 10.0,
                "window_overlap_sec": 2.0,
                "in_progress": True,
                "window_index": 1,
                "total_windows": 3,
                "segments": [
                    {"start": 0.0, "end": 10.0, "text": "第一段"},
                ],
            }
            partial_json.write_text(module.json.dumps(partial_payload, ensure_ascii=False, indent=2), encoding="utf-8")
            partial_txt.write_text("00:00 第一段\n", encoding="utf-8")

            transcribe_calls: list[float] = []

            def fake_transcribe_request(_server, _metadata, _audio_path_arg, _language, request_start, request_end):
                transcribe_calls.append(request_start)
                # 返回一个窗口的结果
                if request_start == 8.0:
                    return {"results": [make_result(10.0, "第二段")]}
                if request_start == 16.0:
                    return {"results": [make_result(10.0, "第三段")]}
                raise AssertionError(f"unexpected start: {request_start}")

            with mock.patch.dict(os.environ, {"NIM_API_KEY": "nvapi-test"}, clear=False):
                with mock.patch.object(module, "list_subtitle_streams", return_value=[]):
                    with mock.patch.object(module, "get_audio_info", return_value={"duration": 26.0, "size": 1}):
                        with mock.patch.object(module, "transcribe_request", side_effect=fake_transcribe_request):
                            outputs = module.transcribe_to_files(video_path, "zh-CN")

            # 应当从第2个窗口开始（8.0），跳过已完成的 0.0
            self.assertEqual(transcribe_calls, [8.0, 16.0])
            self.assertTrue(outputs["json"].exists())
            content = outputs["json"].read_text(encoding="utf-8")
            self.assertIn("第一段", content)
            self.assertIn("第二段", content)
            self.assertIn("第三段", content)

    def test_transcribe_to_files_resumes_precisely_by_last_window_start(self):
        module = load_transcribe_module()

        with TemporaryDirectory(dir=PROJECT_ROOT) as tmp_dir_name:
            tmp_dir = Path(tmp_dir_name)
            video_path = tmp_dir / "sample.mp4"
            video_path.write_bytes(b"video")
            video_path.with_suffix(".wav").write_bytes(b"audio")

            output_dir = tmp_dir / "sample"
            output_dir.mkdir(exist_ok=True)
            partial_json = output_dir / "sample.json.partial"

            # 模拟：partial 里 segments 的 end 很不可靠（比如 3.0），但记录了 last_window_start=8.0
            partial_payload = {
                "source": str(video_path),
                "output_dir": str(output_dir),
                "language": "zh-CN",
                "source_type": "asr:nim",
                "window_duration_sec": 10.0,
                "window_overlap_sec": 2.0,
                "in_progress": True,
                "window_index": 2,
                "total_windows": 3,
                "last_window_start": 8.0,
                "last_window_end": 18.0,
                "segments": [
                    {"start": 0.0, "end": 3.0, "text": "第一段"},
                    {"start": 8.0, "end": 3.0, "text": "第二段"},
                ],
            }
            partial_json.write_text(module.json.dumps(partial_payload, ensure_ascii=False, indent=2), encoding="utf-8")

            transcribe_calls: list[float] = []

            def fake_transcribe_request(_server, _metadata, _audio_path_arg, _language, request_start, request_end):
                transcribe_calls.append(request_start)
                # 只应请求最后一个窗口 16.0
                if request_start == 16.0:
                    return {"results": [make_result(10.0, "第三段")]}
                raise AssertionError(f"unexpected start: {request_start}")

            with mock.patch.dict(os.environ, {"NIM_API_KEY": "nvapi-test"}, clear=False):
                with mock.patch.object(module, "list_subtitle_streams", return_value=[]):
                    with mock.patch.object(module, "get_audio_info", return_value={"duration": 26.0, "size": 1}):
                        with mock.patch.object(module, "transcribe_request", side_effect=fake_transcribe_request):
                            outputs = module.transcribe_to_files(video_path, "zh-CN")

            self.assertEqual(transcribe_calls, [16.0])
            self.assertTrue(outputs["json"].exists())

    def test_get_nvidia_api_key_prefers_key_file(self):
        module = load_transcribe_module()

        with mock.patch.dict(os.environ, {"NIM_API_KEY": "nvapi-env"}, clear=False):
            with mock.patch.object(module.Path, "home", return_value=Path("/home/test")):
                with mock.patch.object(module, "_read_key_file", return_value="nvapi-file"):
                    self.assertEqual(module.get_nvidia_api_key(), "nvapi-file")

    def test_get_nvidia_api_key_falls_back_to_env(self):
        module = load_transcribe_module()

        with mock.patch.dict(os.environ, {"NIM_API_KEY": "nvapi-env"}, clear=True):
            with mock.patch.object(module.Path, "home", return_value=Path("/home/test")):
                with mock.patch.object(module, "_read_key_file", return_value=None):
                    self.assertEqual(module.get_nvidia_api_key(), "nvapi-env")

    def test_read_key_file_supports_raw_and_prefixed_format(self):
        module = load_transcribe_module()

        with TemporaryDirectory(dir=PROJECT_ROOT) as tmp_dir_name:
            tmp_dir = Path(tmp_dir_name)
            raw_key_path = tmp_dir / "raw.key"
            prefixed_key_path = tmp_dir / "prefixed.key"

            raw_key_path.write_text("nvapi-raw-key\n", encoding="utf-8")
            prefixed_key_path.write_text("NIM_API_KEY=nvapi-prefixed-key\n", encoding="utf-8")

            self.assertEqual(module._read_key_file(raw_key_path), "nvapi-raw-key")
            self.assertEqual(module._read_key_file(prefixed_key_path), "nvapi-prefixed-key")

    def test_choose_subtitle_stream_prefers_language_mapping(self):
        module = load_transcribe_module()

        streams = [
            module.SubtitleStream(subtitle_position=0, global_index=2, codec_name="subrip", language="eng", title="English"),
            module.SubtitleStream(subtitle_position=1, global_index=3, codec_name="subrip", language="zho", title="中文字幕"),
            module.SubtitleStream(subtitle_position=2, global_index=4, codec_name="ass", language="", title=""),
        ]
        chosen = module.choose_subtitle_stream(streams, "zh-CN")
        self.assertIsNotNone(chosen)
        self.assertEqual(chosen.global_index, 3)

        chosen_en = module.choose_subtitle_stream(streams, "en-US")
        self.assertIsNotNone(chosen_en)
        self.assertEqual(chosen_en.global_index, 2)

    def test_parse_srt_to_segments_basic(self):
        module = load_transcribe_module()

        srt = """1\n00:00:01,000 --> 00:00:03,500\n你好 <i>世界</i>\n\n2\n00:00:04,000 --> 00:00:05,000\n第二行\\N换行\n"""
        segments = module.parse_srt_to_segments(srt)
        self.assertEqual(
            segments,
            [
                {"start": 1.0, "end": 3.5, "text": "你好 世界"},
                {"start": 4.0, "end": 5.0, "text": "第二行 换行"},
            ],
        )

    def test_transcribe_main_does_not_generate_markdown(self):
        module = load_transcribe_module()

        with TemporaryDirectory(dir=PROJECT_ROOT) as tmp_dir_name:
            tmp_dir = Path(tmp_dir_name)
            json_path = tmp_dir / "out.json"
            md_path = tmp_dir / "out.md"
            txt_path = tmp_dir / "out.txt"

            json_path.write_text(
                (
                    "{\n"
                    "  \"source\": \"/tmp/fake.mp4\",\n"
                    "  \"language\": \"zh-CN\",\n"
                    "  \"segments\": [\n"
                    "    {\"start\": 0.0, \"end\": 1.0, \"text\": \"你好世界\"}\n"
                    "  ]\n"
                    "}\n"
                ),
                encoding="utf-8",
            )

            def fake_transcribe_to_files(_video_path, _language):
                return {
                    "txt": txt_path,
                    "json": json_path,
                    "md": md_path,
                    "lines": 1,
                }

            argv_backup = list(module.sys.argv)
            try:
                module.sys.argv = ["transcribe.py", "/tmp/fake.mp4", "zh-CN"]
                with mock.patch.object(module, "transcribe_to_files", side_effect=fake_transcribe_to_files):
                    module.main()
            finally:
                module.sys.argv = argv_backup

            self.assertFalse(md_path.exists())
