import pandas as pd

from analytics.dashboard_answers import answer_question


def _data():
    return pd.DataFrame([
        {"branch_id": "BR-01", "rm_id": "RM-103", "product_code": "credit_card", "customer_id": "C1", "amount": 100, "volume_units": 1},
        {"branch_id": "BR-01", "rm_id": "RM-108", "product_code": "credit_card", "customer_id": "C2", "amount": 200, "volume_units": 2},
        {"branch_id": "BR-02", "rm_id": "RM-201", "product_code": "salary_account", "customer_id": "C3", "amount": 300, "volume_units": 3},
    ])


def test_admin_can_compare_branches():
    answer = answer_question("Compare branches", _data(), "admin")
    assert "BR-01" in answer and "BR-02" in answer


def test_branch_head_can_compare_rms():
    answer = answer_question("Compare RM performance", _data(), "branch_head")
    assert "RM-103" in answer and "RM-108" in answer


def test_rm_cannot_compare_branches():
    answer = answer_question("Compare branches", _data(), "relationship_manager")
    assert "restricted" in answer.lower()