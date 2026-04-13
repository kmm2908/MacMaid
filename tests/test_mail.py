from unittest.mock import patch
from modules.mail import scan

def test_scan_finds_mail_cache(tmp_path):
    mail_dir = tmp_path / "Mail"
    mail_dir.mkdir()
    attach = mail_dir / "Attachments"
    attach.mkdir()
    (attach / "doc.pdf").write_bytes(b"x" * 5000)

    with patch("modules.mail.MAIL_DIR", str(mail_dir)):
        result = scan()

    assert result["category"] == "Mail Store"
    assert result["risk"] == "review"
    assert result["total_size_bytes"] >= 5000

def test_scan_no_mail_dir(tmp_path):
    with patch("modules.mail.MAIL_DIR", str(tmp_path / "NoMail")):
        result = scan()
    assert result["items"] == []
