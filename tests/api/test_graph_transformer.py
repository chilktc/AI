"""graph_transformer 단위 테스트.

validate_group, intensity_to_val, transform_got_to_graph_data,
calc_category_distribution의 변환 정합성을 검증한다.
"""

from __future__ import annotations

from src.api.graph_transformer import (
    VALID_GROUPS,
    calc_category_distribution,
    intensity_to_val,
    transform_got_to_graph_data,
    validate_group,
)

# ===================================================================
# validate_group
# ===================================================================


class TestValidateGroup:
    def test_valid_group_returns_as_is(self) -> None:
        for group in VALID_GROUPS:
            assert validate_group({"group": group}) == group

    def test_invalid_group_with_keyword_fallback(self) -> None:
        node = {"group": "invalid_group", "label": "상사 압박"}
        assert validate_group(node) == "leadership"

    def test_invalid_group_no_keyword_returns_default(self) -> None:
        node = {"group": "invalid_group", "label": "알 수 없는 내용"}
        assert validate_group(node) == "emotional_exhaustion"

    def test_missing_group_with_keyword(self) -> None:
        node = {"label": "번아웃 증상"}
        assert validate_group(node) == "emotional_exhaustion"

    def test_missing_group_and_label(self) -> None:
        assert validate_group({}) == "emotional_exhaustion"

    def test_empty_group_string(self) -> None:
        node = {"group": "", "label": "성장정체 느낌"}
        assert validate_group(node) == "career_growth"

    def test_keyword_priority_first_match(self) -> None:
        """KEYWORD_MAP 순서대로 첫 매칭이 반환된다."""
        node = {"group": "xxx", "label": "과부하"}
        assert validate_group(node) == "work_structure"


# ===================================================================
# intensity_to_val
# ===================================================================


class TestIntensityToVal:
    def test_high_intensity(self) -> None:
        assert intensity_to_val(0.75) == 100
        assert intensity_to_val(1.0) == 100
        assert intensity_to_val(0.9) == 100

    def test_medium_intensity(self) -> None:
        assert intensity_to_val(0.45) == 50
        assert intensity_to_val(0.74) == 50
        assert intensity_to_val(0.5) == 50

    def test_low_intensity(self) -> None:
        assert intensity_to_val(0.44) == 20
        assert intensity_to_val(0.0) == 20
        assert intensity_to_val(0.1) == 20

    def test_returns_int(self) -> None:
        result = intensity_to_val(0.8)
        assert isinstance(result, int)


# ===================================================================
# transform_got_to_graph_data
# ===================================================================


class TestTransformGotToGraphData:
    def test_basic_transformation(self) -> None:
        got = {
            "nodes": [
                {"id": 1, "label": "업무 과부하", "group": "work_structure", "intensity": 0.8},
                {"id": 2, "label": "상사 갈등", "group": "leadership", "intensity": 0.5},
                {"id": 3, "label": "동료 신뢰", "group": "peer_relations", "intensity": 0.3},
            ],
            "edges": [
                {"from": 1, "to": 2},
                {"from": 2, "to": 3},
            ],
        }
        result = transform_got_to_graph_data(got)

        assert len(result["nodes"]) == 3
        assert len(result["links"]) == 2

    def test_id_prefix_mapping(self) -> None:
        got = {
            "nodes": [
                {"id": 1, "label": "test", "group": "work_structure", "intensity": 0.5},
            ],
            "edges": [],
        }
        result = transform_got_to_graph_data(got)
        assert result["nodes"][0]["id"] == "b1"

    def test_same_group_sequential_ids(self) -> None:
        got = {
            "nodes": [
                {"id": 1, "label": "a", "group": "work_structure", "intensity": 0.5},
                {"id": 2, "label": "b", "group": "work_structure", "intensity": 0.6},
                {"id": 3, "label": "c", "group": "work_structure", "intensity": 0.7},
            ],
            "edges": [],
        }
        result = transform_got_to_graph_data(got)
        ids = [n["id"] for n in result["nodes"]]
        assert ids == ["b1", "b2", "b3"]

    def test_different_groups_get_different_prefixes(self) -> None:
        got = {
            "nodes": [
                {"id": 1, "label": "a", "group": "work_structure", "intensity": 0.5},
                {"id": 2, "label": "b", "group": "leadership", "intensity": 0.5},
                {"id": 3, "label": "c", "group": "career_growth", "intensity": 0.5},
            ],
            "edges": [],
        }
        result = transform_got_to_graph_data(got)
        ids = [n["id"] for n in result["nodes"]]
        assert ids == ["b1", "p1", "g1"]

    def test_empty_input(self) -> None:
        result = transform_got_to_graph_data({})
        assert result == {"nodes": [], "links": []}

    def test_edge_with_missing_node_skipped(self) -> None:
        got = {
            "nodes": [
                {"id": 1, "label": "a", "group": "work_structure", "intensity": 0.5},
            ],
            "edges": [
                {"from": 1, "to": 999},  # 999 노드 없음
            ],
        }
        result = transform_got_to_graph_data(got)
        assert len(result["links"]) == 0

    def test_link_source_target_mapping(self) -> None:
        got = {
            "nodes": [
                {"id": 1, "label": "a", "group": "work_structure", "intensity": 0.5},
                {"id": 2, "label": "b", "group": "leadership", "intensity": 0.5},
            ],
            "edges": [{"from": 1, "to": 2}],
        }
        result = transform_got_to_graph_data(got)
        link = result["links"][0]
        assert link["source"] == "b1"
        assert link["target"] == "p1"

    def test_node_name_from_label(self) -> None:
        got = {
            "nodes": [
                {"id": 1, "label": "업무 스트레스", "group": "work_structure", "intensity": 0.5},
            ],
            "edges": [],
        }
        result = transform_got_to_graph_data(got)
        assert result["nodes"][0]["name"] == "업무 스트레스"

    def test_intensity_to_val_applied(self) -> None:
        got = {
            "nodes": [
                {"id": 1, "label": "a", "group": "work_structure", "intensity": 0.9},
            ],
            "edges": [],
        }
        result = transform_got_to_graph_data(got)
        assert result["nodes"][0]["val"] == 100

    def test_default_intensity(self) -> None:
        """intensity 미제공 시 기본값 0.5 → val 50."""
        got = {
            "nodes": [{"id": 1, "label": "a", "group": "work_structure"}],
            "edges": [],
        }
        result = transform_got_to_graph_data(got)
        assert result["nodes"][0]["val"] == 50


# ===================================================================
# calc_category_distribution
# ===================================================================


class TestCalcCategoryDistribution:
    def test_normal_distribution(self) -> None:
        nodes = [
            {"group": "peer_relations"},
            {"group": "peer_relations"},
            {"group": "work_structure"},
        ]
        dist = calc_category_distribution(nodes)
        assert dist == {"peer_relations": 2, "work_structure": 1}

    def test_empty_list(self) -> None:
        assert calc_category_distribution([]) == {}

    def test_missing_group_defaults(self) -> None:
        nodes = [{"name": "no group"}]
        dist = calc_category_distribution(nodes)
        assert dist == {"emotional_exhaustion": 1}


class TestTransformCumulativeToFrontend:
    """RDB 누적 그래프 → 프론트엔드 변환 테스트."""

    def test_basic_transformation(self) -> None:
        from src.api.graph_transformer import transform_cumulative_to_frontend

        nodes = [
            {"label": "업무과부하", "grp": "work_structure", "weight": 0.81, "mention_count": 3, "trend": "increasing", "first_seen": "2026-03-20", "last_seen": "2026-04-05"},
        ]
        edges: list[dict] = []
        result = transform_cumulative_to_frontend(nodes, edges)
        assert len(result["nodes"]) == 1
        assert result["nodes"][0]["name"] == "업무과부하"
        assert result["nodes"][0]["group"] == "work_structure"

    def test_id_prefix_mapping(self) -> None:
        from src.api.graph_transformer import transform_cumulative_to_frontend

        nodes = [
            {"label": "A", "grp": "work_structure", "weight": 0.5},
            {"label": "B", "grp": "leadership", "weight": 0.6},
            {"label": "C", "grp": "emotional_exhaustion", "weight": 0.7},
        ]
        result = transform_cumulative_to_frontend(nodes, [])
        ids = [n["id"] for n in result["nodes"]]
        assert ids == ["b1", "p1", "br1"]

    def test_weight_raw_value_no_val_field(self) -> None:
        from src.api.graph_transformer import transform_cumulative_to_frontend

        nodes = [{"label": "번아웃", "grp": "emotional_exhaustion", "weight": 0.83}]
        result = transform_cumulative_to_frontend(nodes, [])
        node = result["nodes"][0]
        assert node["weight"] == 0.83
        assert "val" not in node  # val 필드 없음

    def test_edge_mapping_by_label_grp(self) -> None:
        from src.api.graph_transformer import transform_cumulative_to_frontend

        nodes = [
            {"label": "A", "grp": "work_structure", "weight": 0.5},
            {"label": "B", "grp": "leadership", "weight": 0.6},
        ]
        edges = [
            {"source_label": "A", "source_grp": "work_structure", "target_label": "B", "target_grp": "leadership", "weight": 3},
        ]
        result = transform_cumulative_to_frontend(nodes, edges)
        assert len(result["links"]) == 1
        assert result["links"][0]["source"] == "b1"
        assert result["links"][0]["target"] == "p1"
        assert result["links"][0]["weight"] == 3

    def test_empty_input(self) -> None:
        from src.api.graph_transformer import transform_cumulative_to_frontend

        result = transform_cumulative_to_frontend([], [])
        assert result == {"nodes": [], "links": []}

    def test_metadata_preserved(self) -> None:
        from src.api.graph_transformer import transform_cumulative_to_frontend

        nodes = [
            {"label": "X", "grp": "career_growth", "weight": 0.4, "mention_count": 5, "trend": "decreasing", "first_seen": "2026-01-01", "last_seen": "2026-04-01"},
        ]
        result = transform_cumulative_to_frontend(nodes, [])
        node = result["nodes"][0]
        assert node["mention_count"] == 5
        assert node["trend"] == "decreasing"
        assert node["first_seen"] == "2026-01-01"
        assert node["last_seen"] == "2026-04-01"

    def test_self_loop_edge_filtered(self) -> None:
        from src.api.graph_transformer import transform_cumulative_to_frontend

        nodes = [{"label": "A", "grp": "work_structure", "weight": 0.5}]
        edges = [{"source_label": "A", "source_grp": "work_structure", "target_label": "A", "target_grp": "work_structure", "weight": 1}]
        result = transform_cumulative_to_frontend(nodes, edges)
        assert len(result["links"]) == 0

    def test_invalid_group_corrected(self) -> None:
        from src.api.graph_transformer import transform_cumulative_to_frontend

        nodes = [{"label": "번아웃", "grp": "INVALID", "weight": 0.5}]
        result = transform_cumulative_to_frontend(nodes, [])
        assert result["nodes"][0]["group"] == "emotional_exhaustion"
