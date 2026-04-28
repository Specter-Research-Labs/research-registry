from __future__ import annotations

from atp.coq.serapi import extract_feedback_strings


def test_extract_feedback_strings_decodes_str_tokens() -> None:
    responses = [
        ["Answer", "2", "Ack"],
        [
            "Feedback",
            [
                ["doc_id", "0"],
                [
                    "contents",
                    ["Message", ["str\"Nat.add_0_l\\n     : forall n : nat, 0 + n = n\""]],
                ],
            ],
        ],
        ["Answer", "2", "Completed"],
    ]

    out = extract_feedback_strings(responses)
    assert out == ["Nat.add_0_l\n     : forall n : nat, 0 + n = n"]


def test_extract_feedback_strings_ignores_non_message_tokens() -> None:
    responses = [
        ["Answer", "1", "Ack"],
        ["Feedback", [["contents", "Processed"]]],
        ["Answer", "1", "Completed"],
    ]
    assert extract_feedback_strings(responses) == []
