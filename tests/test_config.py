"""Config 테스트."""
import os
import pytest
from config import Config


class TestConfigDefaults:
    def test_default_values(self):
        cfg = Config()
        assert cfg.is_paper is True
        assert cfg.swing_n == 3
        assert cfg.ob_lookback == 30
        assert cfg.rvol_threshold == 1.3  # 완화됨 (1.5 → 1.3)
        assert cfg.rvol_window == 20
        assert cfg.min_r_pct == 0.2  # 신규 필드
        assert cfg.scan_interval == 180
        assert cfg.scan_start == "0905"
        assert cfg.scan_end == "1525"
        assert cfg.acnt_prdt_cd == "01"

    def test_base_url_paper(self):
        cfg = Config(is_paper=True)
        assert cfg.base_url == "https://openapivts.koreainvestment.com:29443"

    def test_base_url_real(self):
        cfg = Config(is_paper=False)
        assert cfg.base_url == "https://openapi.koreainvestment.com:9443"

    def test_tr_id_min5_paper(self):
        cfg = Config(is_paper=True)
        assert cfg.tr_id("min5") == "FHKST03010200"

    def test_tr_id_min5_real(self):
        cfg = Config(is_paper=False)
        assert cfg.tr_id("min5") == "FHKST03010200"

    def test_tr_id_vol_rank(self):
        cfg = Config(is_paper=True)
        assert cfg.tr_id("vol_rank") == "FHPST01710000"


class TestConfigFromEnv:
    def test_from_env_with_account_dash(self, monkeypatch):
        monkeypatch.setenv("KIS_APP_KEY", "test_key")
        monkeypatch.setenv("KIS_APP_SECRET", "test_secret")
        monkeypatch.setenv("TELEGRAM_TOKEN", "test_token")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")
        monkeypatch.setenv("KIS_ACCOUNT", "12345678-01")
        cfg = Config.from_env()
        assert cfg.cano == "12345678"
        assert cfg.acnt_prdt_cd == "01"

    def test_from_env_with_account_long(self, monkeypatch):
        monkeypatch.setenv("KIS_APP_KEY", "test_key")
        monkeypatch.setenv("KIS_APP_SECRET", "test_secret")
        monkeypatch.setenv("TELEGRAM_TOKEN", "test_token")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")
        monkeypatch.setenv("KIS_ACCOUNT", "1234567801")
        cfg = Config.from_env()
        assert cfg.cano == "12345678"
        assert cfg.acnt_prdt_cd == "01"

    def test_from_env_with_account_short(self, monkeypatch):
        monkeypatch.setenv("KIS_APP_KEY", "test_key")
        monkeypatch.setenv("KIS_APP_SECRET", "test_secret")
        monkeypatch.setenv("TELEGRAM_TOKEN", "test_token")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")
        monkeypatch.setenv("KIS_ACCOUNT", "12345")
        cfg = Config.from_env()
        assert cfg.cano == "12345"

    def test_from_env_with_numeric_override(self, monkeypatch):
        monkeypatch.setenv("TOP_N", "100")
        monkeypatch.setenv("SCAN_INTERVAL", "300")
        monkeypatch.setenv("RVOL_THRESHOLD", "2.0")
        cfg = Config.from_env()
        assert cfg.top_n == 100
        assert cfg.scan_interval == 300
        assert cfg.rvol_threshold == 2.0

    def test_from_env_with_real_trading_enabled(self, monkeypatch):
        monkeypatch.setenv("ENABLE_REAL_TRADING", "1")
        cfg = Config.from_env()
        assert cfg.is_paper is False

    def test_from_env_with_real_trading_yes(self, monkeypatch):
        monkeypatch.setenv("ENABLE_REAL_TRADING", "YES")
        cfg = Config.from_env()
        assert cfg.is_paper is False

    def test_from_env_with_real_trading_true(self, monkeypatch):
        monkeypatch.setenv("ENABLE_REAL_TRADING", "true")
        cfg = Config.from_env()
        assert cfg.is_paper is False

    def test_from_env_with_real_trading_on(self, monkeypatch):
        monkeypatch.setenv("ENABLE_REAL_TRADING", "on")
        cfg = Config.from_env()
        assert cfg.is_paper is False

    def test_from_env_defaults_to_paper(self, monkeypatch):
        monkeypatch.delenv("ENABLE_REAL_TRADING", raising=False)
        cfg = Config.from_env()
        assert cfg.is_paper is True


class TestConfigValidate:
    def test_validate_with_all_required(self):
        cfg = Config(
            app_key="key",
            app_secret="secret",
            telegram_token="token",
            telegram_chat="chat",
            cano="12345678"
        )
        cfg.validate()  # Should not raise

    def test_validate_missing_app_key(self):
        cfg = Config(app_secret="s", telegram_token="t", telegram_chat="c", cano="ca")
        with pytest.raises(ValueError, match="KIS_APP_KEY"):
            cfg.validate()

    def test_validate_missing_app_secret(self):
        cfg = Config(app_key="k", telegram_token="t", telegram_chat="c", cano="ca")
        with pytest.raises(ValueError, match="KIS_APP_SECRET"):
            cfg.validate()

    def test_validate_missing_telegram_token(self):
        cfg = Config(app_key="k", app_secret="s", telegram_chat="c", cano="ca")
        with pytest.raises(ValueError, match="TELEGRAM_TOKEN"):
            cfg.validate()

    def test_validate_missing_telegram_chat(self):
        cfg = Config(app_key="k", app_secret="s", telegram_token="t", cano="ca")
        with pytest.raises(ValueError, match="TELEGRAM_CHAT_ID"):
            cfg.validate()

    def test_validate_missing_cano(self):
        cfg = Config(app_key="k", app_secret="s", telegram_token="t", telegram_chat="c")
        with pytest.raises(ValueError, match="CANO"):
            cfg.validate()

    def test_validate_multiple_missing(self):
        cfg = Config()
        with pytest.raises(ValueError) as exc:
            cfg.validate()
        msg = str(exc.value)
        assert "KIS_APP_KEY" in msg
        assert "KIS_APP_SECRET" in msg
