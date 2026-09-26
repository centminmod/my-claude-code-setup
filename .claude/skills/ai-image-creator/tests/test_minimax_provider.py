"""Tests for the MiniMax text-to-image provider."""

from __future__ import annotations

import base64
import importlib.util
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "generate-image.py"
SPEC = importlib.util.spec_from_file_location("generate_image", SCRIPT_PATH)
assert SPEC and SPEC.loader
generate_image = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(generate_image)


class MiniMaxProviderTests(unittest.TestCase):
    def test_resolve_model_uses_default_and_accepts_live_model(self) -> None:
        self.assertEqual(
            generate_image.resolve_model(None, "minimax"),
            ("image-01", ["image"]),
        )
        self.assertEqual(
            generate_image.resolve_model("image-01-live", "minimax"),
            ("image-01-live", ["image"]),
        )

    def test_direct_urls_cover_both_regions(self) -> None:
        self.assertEqual(
            generate_image.build_direct_url("minimax", "image-01", "global"),
            "https://api.minimax.io/v1/image_generation",
        )
        self.assertEqual(
            generate_image.build_direct_url("minimax", "image-01", "cn"),
            "https://api.minimaxi.com/v1/image_generation",
        )

    def test_headers_use_bearer_authorization(self) -> None:
        headers = generate_image.build_headers(
            "minimax", "direct", {"direct_key": "test-value"}
        )
        self.assertEqual(headers["Authorization"], "Bearer test-value")

    def test_request_body_includes_supported_text_to_image_fields(self) -> None:
        body = generate_image.build_request_body(
            "minimax",
            "image-01-live",
            "A lighthouse at dawn",
            aspect_ratio="16:9",
            response_format="base64",
            width=1920,
            height=1080,
            seed=42,
            num_images=2,
            prompt_optimizer=False,
            subject_references=["https://example.invalid/subject.png"],
        )
        self.assertEqual(
            body,
            {
                "model": "image-01-live",
                "prompt": "A lighthouse at dawn",
                "aspect_ratio": "16:9",
                "width": 1920,
                "height": 1080,
                "response_format": "base64",
                "seed": 42,
                "n": 2,
                "prompt_optimizer": False,
                "subject_reference": [
                    {
                        "type": "character",
                        "image_file": "https://example.invalid/subject.png",
                    }
                ],
            },
        )

    def test_extracts_base64_response(self) -> None:
        expected = b"image-bytes"
        response = {
            "data": {"image_urls": [base64.b64encode(expected).decode()]},
            "base_resp": {"status_code": 0},
        }
        self.assertEqual(
            generate_image.extract_image_minimax(response),
            (expected, ""),
        )

    def test_downloads_url_response(self) -> None:
        class RemoteImage:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self) -> bytes:
                return b"downloaded-image"

        response = {
            "data": {"image_urls": ["https://example.invalid/image.png"]},
            "base_resp": {"status_code": 0},
        }
        with mock.patch.object(
            generate_image.urllib.request, "urlopen", return_value=RemoteImage()
        ):
            self.assertEqual(
                generate_image.extract_image_minimax(response),
                (b"downloaded-image", ""),
            )

    def test_surfaces_api_error(self) -> None:
        response = {
            "base_resp": {"status_code": 1001, "status_msg": "request rejected"}
        }
        with self.assertRaisesRegex(RuntimeError, "request rejected"):
            generate_image.extract_image_minimax(response)


if __name__ == "__main__":
    unittest.main()
