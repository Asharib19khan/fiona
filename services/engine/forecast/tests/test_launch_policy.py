import pytest

from engine.forecast.launch_lab.policy import LaunchPolicy, PolicySource, load_policy


def test_defaults_are_labelled_as_drafts(tmp_path):
    policy, sources = load_policy(tmp_path / "missing.yaml")
    assert policy == LaunchPolicy()
    assert set(sources.values()) == {PolicySource.DRAFT_DEFAULT}


def test_rulebook_basis_points_then_owner_overrides(tmp_path):
    path = tmp_path / "launch_lab.yaml"
    path.write_text(
        "launch_lab:\n"
        "  min_contribution_margin_bp: 2500\n"
        "  launch_ramp_bp: [5000, 10000]\n"
        "  demand_sigma_bp: {own_history: 1500, comparable_history: 3000, user_estimate: 6000}\n"
        "  cost_shock_bp: [-300, 0, 800]\n"
        "  breakeven_horizon_months: 9\n",
        encoding="utf-8",
    )
    policy, sources = load_policy(
        path, {"max_loss_probability_bp": 2000, "max_investment_minor": 5_000_000_00}
    )
    assert policy.min_contribution_margin == pytest.approx(0.25)
    assert policy.launch_ramp == pytest.approx([0.5, 1.0])
    assert policy.demand_sigma.user_estimate == pytest.approx(0.6)
    assert policy.cost_shock == pytest.approx((-0.03, 0.0, 0.08))
    assert policy.breakeven_horizon_months == 9
    assert policy.max_loss_probability == pytest.approx(0.2)
    assert sources["min_contribution_margin"] is PolicySource.RULEBOOK
    assert sources["max_loss_probability"] is PolicySource.OWNER
    assert sources["seed"] is PolicySource.DRAFT_DEFAULT


def test_unknown_rulebook_keys_fail_loudly(tmp_path):
    path = tmp_path / "launch_lab.yaml"
    path.write_text("launch_lab:\n  min_margin_typo_bp: 2000\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unknown"):
        load_policy(path)


def test_owner_cannot_change_modelling_assumptions(tmp_path):
    with pytest.raises(ValueError):
        load_policy(tmp_path / "x.yaml", {"seed": 1})


def test_basis_points_must_be_integers(tmp_path):
    with pytest.raises(ValueError):
        load_policy(tmp_path / "x.yaml", {"max_loss_probability_bp": 0.3})
