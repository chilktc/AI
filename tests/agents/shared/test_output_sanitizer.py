"""output_sanitizer 모듈 테스트.

[보안 담당자 참고]
새 PII 패턴 추가 시 이 파일에도 테스트 케이스를 추가해 주세요.
오탐(false positive) 케이스도 포함하여 일반 텍스트가 잘못 마스킹되지 않는지 확인합니다.
"""
import pytest

from src.agents.shared.output_sanitizer import sanitize_dict_values, sanitize_output


# === 정탐(True Positive) 테스트 ===


class TestPhoneKrMobile:
    """한국 휴대전화 번호 감지."""

    def test_with_hyphens(self) -> None:
        text = "연락처는 010-1234-5678입니다"
        result, detected = sanitize_output(text)
        assert "phone_kr_mobile" in detected
        assert "010-1234-5678" not in result
        assert "[휴대전화_마스킹]" in result

    def test_without_hyphens(self) -> None:
        text = "전화번호 01012345678로 연락주세요"
        result, detected = sanitize_output(text)
        assert "phone_kr_mobile" in detected

    def test_old_prefix_011(self) -> None:
        text = "011-234-5678"
        result, detected = sanitize_output(text)
        assert "phone_kr_mobile" in detected


class TestRrnKr:
    """한국 주민등록번호 감지."""

    def test_with_hyphen(self) -> None:
        text = "주민번호 900101-1234567"
        result, detected = sanitize_output(text)
        assert "rrn_kr" in detected
        assert "[주민번호_마스킹]" in result

    def test_without_hyphen(self) -> None:
        text = "9001011234567"
        result, detected = sanitize_output(text)
        assert "rrn_kr" in detected


class TestEmail:
    """이메일 주소 감지."""

    def test_standard(self) -> None:
        text = "이메일: user@example.com"
        result, detected = sanitize_output(text)
        assert "email" in detected
        assert "[이메일_마스킹]" in result


class TestLandline:
    """한국 유선전화 번호 감지."""

    def test_seoul(self) -> None:
        text = "사무실 02-1234-5678"
        result, detected = sanitize_output(text)
        assert "phone_kr_landline" in detected

    def test_gyeonggi(self) -> None:
        text = "경기 031-123-4567"
        result, detected = sanitize_output(text)
        assert "phone_kr_landline" in detected


class TestCardNumber:
    """신용카드 번호 감지."""

    def test_with_hyphens(self) -> None:
        text = "카드번호 1234-5678-9012-3456"
        result, detected = sanitize_output(text)
        assert "card_number" in detected
        assert "[카드번호_마스킹]" in result


# === 오탐(False Positive) 방지 테스트 ===


class TestFalsePositives:
    """일반 텍스트가 잘못 마스킹되지 않는지 확인."""

    def test_normal_korean_text(self) -> None:
        text = "오늘 하루도 수고했어요. 내일은 더 좋은 날이 될 거예요."
        result, detected = sanitize_output(text)
        assert detected == []
        assert result == text

    def test_short_numbers(self) -> None:
        text = "3시에 만나요. 5개 사세요."
        result, detected = sanitize_output(text)
        assert detected == []

    def test_date_format(self) -> None:
        text = "2026-03-31에 만나요"
        result, detected = sanitize_output(text)
        assert "rrn_kr" not in detected

    def test_empty_string(self) -> None:
        result, detected = sanitize_output("")
        assert result == ""
        assert detected == []


# === 복합 테스트 ===


class TestMultiplePII:
    """여러 PII가 동시에 포함된 경우."""

    def test_phone_and_email(self) -> None:
        text = "전화: 010-1234-5678, 이메일: hong@test.com"
        result, detected = sanitize_output(text)
        assert "phone_kr_mobile" in detected
        assert "email" in detected
        assert "010-1234-5678" not in result
        assert "hong@test.com" not in result


# === dict 정제 테스트 ===


class TestSanitizeDict:
    """dict 내 문자열 값 정제."""

    def test_target_keys_only(self) -> None:
        data = {
            "script_text": "전화 010-1234-5678로 상담하세요",
            "episode_title": "멘탈케어 에피소드",
            "duration": 300,
        }
        result = sanitize_dict_values(data, target_keys=["script_text"])
        assert "[휴대전화_마스킹]" in result["script_text"]
        assert result["episode_title"] == "멘탈케어 에피소드"
        assert result["duration"] == 300

    def test_nested_dict(self) -> None:
        data = {
            "segments": [
                {"script_text": "연락처 010-9999-8888", "type": "intro"},
            ],
        }
        result = sanitize_dict_values(data, target_keys=["script_text"])
        assert "[휴대전화_마스킹]" in result["segments"][0]["script_text"]
        assert result["segments"][0]["type"] == "intro"

    def test_list_of_strings(self) -> None:
        data = {
            "key_insights": [
                "user@example.com으로 연락하세요",
                "좋은 아침입니다",
            ],
        }
        result = sanitize_dict_values(data, target_keys=["key_insights"])
        assert "[이메일_마스킹]" in result["key_insights"][0]
        assert result["key_insights"][1] == "좋은 아침입니다"
