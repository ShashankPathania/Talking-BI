"""Planner that decides which stages need to run."""

from app.core.state import ExecutionPlan, QueryResult, QueryState


class QueryPlanner:
    def build(
        self,
        previous_state: QueryState | None,
        state: QueryState,
        previous_result: QueryResult | None,
    ) -> ExecutionPlan:
        changed_sections = self._changed_sections(previous_state, state)
        update_visualization_only = (
            previous_result is not None
            and set(changed_sections).issubset({"intent", "visualization"})
            and "visualization" in changed_sections
        )
        reuse_previous_data = (
            previous_result is not None
            and not any(section in changed_sections for section in ["data", "transformation"])
        )
        run_analysis = not update_visualization_only

        execution_mode = "sql" if state.data.source_type == "database" else "pandas"
        if state.data.source_type == "unknown":
            execution_mode = "pandas"

        steps: list[str] = []
        if not update_visualization_only and not reuse_previous_data:
            steps.extend(["load_data", "transform_data"])
        elif reuse_previous_data:
            steps.append("reuse_previous_result")
        if run_analysis:
            steps.append("analyze_data")
        steps.append("build_chart")

        if update_visualization_only:
            rationale = "Only visualization settings changed, so the planner reuses the prior result."
        elif reuse_previous_data:
            rationale = "Data shape is unchanged, so the planner reuses the prior result and recomputes analysis/chart output."
        else:
            rationale = "Data or transformation state changed, so the planner performs a fresh fetch and transformation pass."

        return ExecutionPlan(
            needs_new_fetch=not reuse_previous_data,
            reuse_previous_data=reuse_previous_data,
            run_analysis=run_analysis,
            update_visualization_only=update_visualization_only,
            execution_mode=execution_mode,
            steps=steps,
            changed_sections=changed_sections,
            rationale=rationale,
        )

    @staticmethod
    def _changed_sections(
        previous_state: QueryState | None,
        current_state: QueryState,
    ) -> list[str]:
        if previous_state is None:
            return ["intent", "data", "transformation", "analysis", "visualization"]

        changed: list[str] = []
        for section in ["intent", "data", "transformation", "analysis", "visualization"]:
            if getattr(previous_state, section).model_dump() != getattr(current_state, section).model_dump():
                changed.append(section)
        return changed
