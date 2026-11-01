from app.attachments import MAX_FILE_SIZE_MB, validate_attachment

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


def test_valid_png_is_accepted():
    attachment = validate_attachment("screen.png", PNG)
    assert attachment and attachment.mime_type == "image/png"


def test_extension_not_on_whitelist_is_rejected():
    assert validate_attachment("malware.exe", b"MZ\x90\x00") is None


def test_spoofed_extension_is_rejected():
    assert validate_attachment("invoice.pdf", PNG) is None


def test_oversized_file_is_rejected():
    assert validate_attachment("big.pdf", b"%PDF" + b"0" * (MAX_FILE_SIZE_MB * 1024 * 1024)) is None


def test_webp_and_wav_need_full_riff_header():
    assert validate_attachment("a.webp", b"RIFF\x00\x00\x00\x00WEBPVP8 ") is not None
    assert validate_attachment("a.wav", b"RIFF\x00\x00\x00\x00WEBPVP8 ") is None


def test_directory_components_are_stripped_from_filename():
    assert validate_attachment("../../etc/x.png", PNG).filename == "x.png"

def test_valid_m4a_is_accepted():
    m4a_header = b"\x00\x00\x00\x20ftypM4A " + b"\x00" * 32
    assert validate_attachment("recording.m4a", m4a_header) is not None
