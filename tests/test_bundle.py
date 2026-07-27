"""Guard test: the built bundle must be correct for the layout it lands in.

One documented PYTHONPATH has to serve three layouts (repo root, plugin
install, standalone bundle) and can only be authored for one of them, so the
bundle rewrites the copies. A README whose first command names a directory
that does not exist inside the bundle is a broken first impression, and it was
broken in exactly that way before this test existed.

Runs `bash scripts/build_bundle.sh` into a tmp dir. No network, no installs.
"""
import os
import subprocess

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
SCRIPT = os.path.join(ROOT, "scripts", "build_bundle.sh")


def _build(tmp_path):
    out = tmp_path / "bundle"
    env = dict(os.environ, OUT=str(out))
    proc = subprocess.run(["bash", SCRIPT], cwd=ROOT, env=env,
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    return out


def _read(path):
    return path.read_text(encoding="utf-8")


def test_bundle_pythonpath_resolves_inside_the_bundle(tmp_path):
    out = _build(tmp_path)
    for name in ("SKILL.md", "README.md"):
        text = _read(out / name)
        assert "PYTHONPATH=scripts" in text, name
        # Neither of the other two layouts' paths exists here.
        assert "CLAUDE_PLUGIN_ROOT" not in text, name
        assert "crm-report-card/scripts" not in text, name
    assert (out / "scripts" / "crm_report_card" / "cli.py").exists()


def test_bundle_ships_everything_its_skill_cites(tmp_path):
    out = _build(tmp_path)
    assert (out / "properties.yaml").exists()          # cited as the catalogue
    assert (out / "assets" / "icp-scorer-prompt.md").exists()
    assert (out / "fixtures" / "messy-crm-sample.csv").exists()


def test_bundle_does_not_claim_to_ship_tests_or_eval(tmp_path):
    """It excludes both, so the tour must not point downloaders at them."""
    out = _build(tmp_path)
    assert not (out / "tests").exists()
    assert not (out / "eval").exists()
    skill = _read(out / "SKILL.md")
    assert "`tests/` and `eval/`: the proof" not in skill


def test_the_plugin_skill_is_authored_for_a_plugin_install():
    """The plugin copy is read from an install directory, not the user's cwd,
    so a bare `PYTHONPATH=scripts` there resolves against the wrong root."""
    skill = os.path.join(ROOT, "crm-report-card", "skills", "crm-report-card",
                         "SKILL.md")
    with open(skill, encoding="utf-8") as fh:
        text = fh.read()
    assert "PYTHONPATH=scripts " not in text
    assert 'PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts"' in text


def test_the_repo_readme_is_authored_for_a_repo_root_checkout():
    with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as fh:
        text = fh.read()
    assert "PYTHONPATH=crm-report-card/scripts" in text
    assert os.path.isdir(os.path.join(ROOT, "crm-report-card", "scripts"))
