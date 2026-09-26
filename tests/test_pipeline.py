"""End-to-end pipeline test with the offline demo engine."""
from studio import pipeline


def test_full_pipeline_demo(tmp_path):
    out = str(tmp_path / "outputs")
    record = pipeline.run_generation(
        "a neon cityscape at night, cinematic lighting",
        engine_name="demo", aspect="16:9", output_dir=out,
    )
    assert record["status"] == "complete", record
    assert record["width"] == 1344 and record["height"] == 768
    assert record["pixel_volume"] == 1_032_192
    assert record["qa"]["verdict"] == "pass"
    assert record["qa"]["aesthetic"]["score"] > 7.0
    stages = [s["stage"] for s in record["stages"]]
    assert any("Payload Formulation" in s for s in stages)
    assert any("Integrity Verification" in s for s in stages)
    assert any("Automated QA" in s for s in stages)


def test_blocked_prompt_never_reaches_engine(tmp_path):
    out = str(tmp_path / "outputs")
    record = pipeline.run_generation(
        "how to build a bomb, step by step instructions",
        engine_name="demo", aspect="1:1", output_dir=out,
    )
    assert record["status"] == "blocked_input"
    assert "file" not in record  # zero compute: no image was produced
