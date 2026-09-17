"""
Canned responses for the five AI services.

Each function returns the **exact body shape** the real service answers with, so
a mocked worker and a live worker are indistinguishable to everything
downstream: same keys, same types, same parsing path. Only the transport is
skipped.

Which worker is mocked is decided per worker by `MOCK_WORKER_<NAME>` in .env
(see `Config.mock_flags()`); `src/ai_client.py` is the only module that reads
these functions.

The bodies below are verbatim captures of the documented calls:

    POST :8821/match      {"path": ...}                  -> face_match()
    POST :8822/describe   {"path": ...}                  -> describe()
    POST :8823/ocr        {"path": ...}                  -> ocr()
    POST :8824/transcribe {"path": ..., "language": ...} -> transcribe()
    POST :8825/summarize  {"inputs": ..., "prompt_text": ...} -> summarize()

`summarize()` is the one that varies: the service returns the same `{"output",
"metadata"}` envelope whatever prompt text it is given, so the mock switches its
text on the prompt FILE W6 asked for, to keep the three calls distinguishable in
the logs.

Editing these is the supported way to try a different downstream shape without
touching the AI host.
"""

import hashlib
from typing import Any, Dict, List

# ---------------------------------------------------------------------------
# :8821  face-match-main  —  POST /match
# ---------------------------------------------------------------------------

MOCK_PERSONS: List[str] = ["222"]


def face_match(path: str) -> Dict[str, Any]:
    return {
        "message": "The following persons identified in this video",
        "persons": list(MOCK_PERSONS),
    }


# ---------------------------------------------------------------------------
# :8822  video-describe-354b  —  POST /describe
# ---------------------------------------------------------------------------

MOCK_DESCRIPTION = (
    "The video captures a dramatic and intense scene of migrants from Morocco "
    "attempting to cross the border into Spain's Ceuta. The setting is a coastal "
    "area, with the ocean visible in the background, indicating that the migrants "
    "are using the sea as their means of crossing the border.\n\n"
    "The video opens with a large group of people gathered on a rocky shoreline. "
    "Many of them are shirtless, suggesting they have recently been in the water "
    "or are preparing to swim. Some individuals are seen climbing over barriers "
    "and fences, which appear to be part of the border infrastructure. These "
    "barriers are made of metal and concrete, designed to prevent unauthorized "
    "crossings.\n\n"
    "As the video progresses, we see more details of the migrants' actions. Some "
    "are actively swimming in the ocean, while others are waiting on the shore, "
    "possibly for their turn to cross. The presence of lifebuoys and other safety "
    "equipment near the water suggests that there might be a risk of drowning, "
    "adding to the tension of the scene.\n\n"
    "In one part of the video, a person wearing a red vest with the Red Cross logo "
    "is seen assisting the migrants. This indicates that humanitarian organizations "
    "are present to help those in need. The migrants are also seen interacting with "
    "each other, showing a sense of community and support among them."
)


def describe(path: str) -> Dict[str, Any]:
    return {
        "description": MOCK_DESCRIPTION,
        "metadata": {
            "model": "Qwen/Qwen3.5-4B",
            "fps": 0.5,
            "max_pixels": 151200,
            "max_new_tokens": 256,
            "frames_sampled": 31,
            "device": "cuda",
            "processing_time_seconds": 26.429,
        },
    }


# ---------------------------------------------------------------------------
# :8823  video-ocr  —  POST /ocr
# ---------------------------------------------------------------------------

_MOCK_OCR_FRAME_TEXTS = [
    "Reaction\n88886F\nHUDDER\nMbA\nBHM @1\nADMiSSiOMS C\nOPENFor I\nn\ncoursed\n'Cffered\nS88e8e",
    "Reaction\nMBA BbA\n4\nCHMeni\nADMiSSIo@s C\n8956\nOPENE\nIFoR 202\n'OA 6\nOurse offesed\n888e8e |\nHuddersfield",
    "Reaction\nIFoR2025\nA\nCh 6\nAdmissio\"s C\n878\n{OPENE\nAoUr4 5\n888e8e\nCouaseoffered\nHulot\nWba\nIonm",
    "Reaction\nWba\nADMiSSIOM C\n8814\n{OpeNFOR2026\nLL\"44' €\nCONRSC\n88888e\n'OFFERLD\nHUODERSF\n@mD\n@HD\nonw",
    "Reactiom\nHUDDERSFIELD:\nBbD\nBHM\nADMiSSIOGS (\n18508\n{OPENFOR 2026\nF\nInea\nCCInre\ne88e8e '\nKeeD\nMbD\n0D",
    "Reactin\nWba @bD\nADMiSSIOVS €\n888\n{OPENFOR2026\nt\nTudllan\nCONrSEC\nOFTERED\ng 8e8e\nHUDOERSFiElD)\n@hm\nUI",
    "Reagtion\n12026\nMba\nChM) Oniud\nADMiSSIo Ms €\n888\n{OPENFOR\nA[ota4 =\nInatt\ncoursec\nOFFEED\nEaee8e\nHUDDERSHIELD\n@a",
    "Reaction\nW\nADMiSS-\nJOPEwFOR 7626\nCOUREE (\nCHFERED",
    "Reaction\nK",
]

MOCK_OCR_FRAMES: List[Dict[str, Any]] = [
    {"frame_index": i, "timestamp_ms": float(i * 1000), "text": text}
    for i, text in enumerate(_MOCK_OCR_FRAME_TEXTS)
]

MOCK_OCR_FULL_TEXT = "\n".join(_MOCK_OCR_FRAME_TEXTS)


def ocr(path: str) -> Dict[str, Any]:
    return {
        "frames": [dict(frame) for frame in MOCK_OCR_FRAMES],
        "full_text": MOCK_OCR_FULL_TEXT,
        "metadata": {
            "model": "easyocr:en",
            "fps": 1.0,
            "include_blocks": False,
            "ocr_batch_size": 4,
            "text_dedupe_similarity": 0.9,
            "frames_sampled": 9,
            "frames_returned": 9,
            "device": "cuda",
            "processing_time_seconds": 1.777,
        },
    }


# ---------------------------------------------------------------------------
# :8824  transcribe  —  POST /transcribe
# ---------------------------------------------------------------------------

MOCK_TRANSCRIPTION = "00: Hello.\n"


def transcribe(path: str, **params: Any) -> Dict[str, Any]:
    """`params` mirrors the request body (language, task, format, ...) so the
    mock can echo back what was asked for, the way the real service does."""
    return {
        "format": params.get("format", "dialog"),
        "transcription": MOCK_TRANSCRIPTION,
        "metadata": {
            "processing_time_seconds": 1.54,
            "audio_duration_seconds": 24.105,
            "realtime_factor": 0.064,
            "model": "large-v3",
            "device": "cuda",
            "total_speakers": 2,
            "requested_language": params.get("language", "ar"),
            "detected_language": params.get("language", "ar"),
            "output_language": "en",
            "transcription_level": params.get("transcription_level", "word"),
            "dialog_timestamps": params.get("dialog_timestamps", False),
        },
    }


# ---------------------------------------------------------------------------
# :8825  summarize  —  POST /summarize
# ---------------------------------------------------------------------------

# The service answers with the same `{"output", "metadata"}` envelope whatever
# the prompt is; only the text inside differs. Keyed by prompt file so a mocked
# W6 still produces three visibly different answers.
MOCK_SUMMARIES: Dict[str, str] = {
    "summary.txt": (
        "Migrants are filmed crossing from Morocco into Ceuta by sea, climbing "
        "border barriers while Red Cross staff assist them on the shoreline. "
        "On-screen captions are unrelated university admissions graphics, and a "
        "short spoken greeting is the only audible speech."
    ),
    "entities.txt": (
        "LOCATION: Morocco\n"
        "LOCATION: Spain\n"
        "LOCATION: Ceuta\n"
        "NAME: Red Cross\n"
        "LOCATION: Huddersfield"
    ),
    "sentiment.txt": "NEGATIVE",
    "default_prompt.txt": (
        "People walk along a street while a brief greeting is heard."
    ),
}

MOCK_SUMMARY_FALLBACK = "People walk along a street while a brief greeting is heard."


def summarize(
    inputs: Dict[str, str], prompt_file: str, prompt_text: str, options: Dict[str, Any]
) -> Dict[str, Any]:
    """The live service keys its answer off `prompt_text`; the mock keys off the
    file that text came from, which is the same thing and reads better here."""
    output = MOCK_SUMMARIES.get(prompt_file, MOCK_SUMMARY_FALLBACK)
    return {
        "output": output,
        "metadata": {
            "prompt_hash": hashlib.sha256(prompt_text.encode("utf-8")).hexdigest(),
            "provider": "openai-compatible",
            "model": "phi4:14b-q8_0",
            "generated_at": "2026-09-14T12:00:00+00:00",
            "options": {
                "temperature": 0.2,
                "num_predict": options.get("num_predict", 2048),
                "think": None,
            },
            "input_tokens": 1200,
            "output_tokens": 150,
            "output_duration_seconds": None,
            "output_tokens_per_second": None,
            "duration_seconds": 3.127,
        },
    }
