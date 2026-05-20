import unittest

from importlib import import_module


fallbackDecider = import_module("scripts.fallback_decider")


class TestFallbackDecider(unittest.TestCase):
  def test_hit_code_60018(self):
    fixture = {"code": -60018, "msg": "daily quota exceeded"}
    self.assertTrue(fallbackDecider.isMinerUQuotaLikeError(fixture, source="/tmp/a.pdf"))

  def test_hit_code_60019(self):
    fixture = {"code": -60019, "msg": "daily quota exceeded"}
    self.assertTrue(fallbackDecider.isMinerUQuotaLikeError(fixture, source="/tmp/a.pdf"))

  def test_hit_code_60022_only_for_url(self):
    fixture = {"code": -60022, "msg": "网页读取失败"}
    self.assertTrue(
      fallbackDecider.isMinerUQuotaLikeError(fixture, source="https://example.com/a.pdf")
    )

  def test_no_hit_code_60022_for_local_file(self):
    fixture = {"code": -60022, "msg": "网页读取失败"}
    self.assertFalse(fallbackDecider.isMinerUQuotaLikeError(fixture, source="/tmp/a.pdf"))

  def test_exclude_auth_401(self):
    fixture = {"httpStatus": 401, "code": -60018, "msg": "quota"}
    self.assertFalse(fallbackDecider.isMinerUQuotaLikeError(fixture, source="/tmp/a.pdf"))

  def test_exclude_auth_403_from_exception_text(self):
    err = Exception("HTTP 403: forbidden")
    self.assertFalse(fallbackDecider.isMinerUQuotaLikeError(err, source="/tmp/a.pdf"))

  def test_exclude_param_error_shape(self):
    fixture = {"httpStatus": 400, "code": -10001, "msg": "参数错误"}
    self.assertFalse(fallbackDecider.isMinerUQuotaLikeError(fixture, source="/tmp/a.pdf"))

  def test_exclude_file_error_shape(self):
    fixture = {"httpStatus": 400, "code": -10002, "errMsg": "文件不存在"}
    self.assertFalse(fallbackDecider.isMinerUQuotaLikeError(fixture, source="/tmp/a.pdf"))

  def test_uncertain_5xx_no_fallback(self):
    fixture = {"httpStatus": 500, "errMsg": "internal error"}
    self.assertFalse(fallbackDecider.isMinerUQuotaLikeError(fixture, source="/tmp/a.pdf"))

  def test_uncertain_timeout_no_fallback(self):
    err = Exception("timeout")
    self.assertFalse(fallbackDecider.isMinerUQuotaLikeError(err, source="/tmp/a.pdf"))


if __name__ == "__main__":
  unittest.main()
