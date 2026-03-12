"""Forward-run report for persisted simulation runs in SWIM containers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np


@dataclass
class RunVariableStats:
    """Summary statistics for one persisted output variable."""

    name: str
    shape: tuple[int, ...]
    finite_fraction: float
    minimum: float | None
    maximum: float | None
    mean: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "shape": list(self.shape),
            "finite_fraction": round(self.finite_fraction, 6),
            "min": None if self.minimum is None else round(self.minimum, 6),
            "max": None if self.maximum is None else round(self.maximum, 6),
            "mean": None if self.mean is None else round(self.mean, 6),
        }


@dataclass
class RunStateStats:
    """Summary statistics for persisted initial/final state arrays."""

    state_name: str
    finite_fraction: float
    minimum: float | None
    maximum: float | None
    mean: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "state_name": self.state_name,
            "finite_fraction": round(self.finite_fraction, 6),
            "min": None if self.minimum is None else round(self.minimum, 6),
            "max": None if self.maximum is None else round(self.maximum, 6),
            "mean": None if self.mean is None else round(self.mean, 6),
        }


@dataclass
class RunReport:
    """Summary report for a persisted simulation run."""

    container_path: str
    run_id: str
    run_metadata: dict[str, Any]
    provenance_event: dict[str, Any] | None
    variables: list[RunVariableStats] = field(default_factory=list)
    final_state: list[RunStateStats] = field(default_factory=list)
    initial_state: list[RunStateStats] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def n_variables(self) -> int:
        return len(self.variables)

    @property
    def all_outputs_finite(self) -> bool:
        return all(v.finite_fraction == 1.0 for v in self.variables)

    @property
    def all_final_state_finite(self) -> bool:
        return all(s.finite_fraction == 1.0 for s in self.final_state)

    def summary(self) -> str:
        lines = [
            "Run Report",
            f"  Container: {self.container_path}",
            f"  Run: {self.run_id}",
            f"  Profile: {self.run_metadata.get('profile', '?')}",
            f"  Dates: {self.run_metadata.get('start_date', '?')} to {self.run_metadata.get('end_date', '?')}",
            f"  Fields: {self.run_metadata.get('field_count', '?')}  Days: {self.run_metadata.get('n_days', '?')}",
            f"  Outputs: {self.n_variables}  All finite: {self.all_outputs_finite}",
            f"  Final state finite: {self.all_final_state_finite}",
        ]

        if self.variables:
            lines.append("")
            lines.append(f"  {'Variable':<14} {'Finite':>8} {'Min':>10} {'Max':>10} {'Mean':>10}")
            lines.append("  " + "-" * 58)
            for var in self.variables:
                min_text = "None" if var.minimum is None else f"{var.minimum:.3f}"
                max_text = "None" if var.maximum is None else f"{var.maximum:.3f}"
                mean_text = "None" if var.mean is None else f"{var.mean:.3f}"
                lines.append(
                    f"  {var.name:<14} {var.finite_fraction:>8.3f} {min_text:>10} {max_text:>10} {mean_text:>10}"
                )

        return "\n".join(lines)

    def to_json(self) -> dict[str, Any]:
        return {
            "container_path": self.container_path,
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "run_metadata": _json_safe(self.run_metadata),
            "provenance_event": _json_safe(self.provenance_event),
            "n_variables": self.n_variables,
            "all_outputs_finite": self.all_outputs_finite,
            "all_final_state_finite": self.all_final_state_finite,
            "variables": [v.to_dict() for v in self.variables],
            "final_state": [s.to_dict() for s in self.final_state],
            "initial_state": [s.to_dict() for s in self.initial_state],
        }

    def render_html(self, output_path: str | Path) -> Path:
        return render_html_report(self, output_path)

    def render_png(self, output_path: str | Path) -> Path:
        return render_png_report(self, output_path)


def build_run_report(container, run_id: str) -> RunReport:
    """Build a RunReport from a persisted simulation run."""
    run_group = container.runs._get_run_group(run_id)
    metadata = dict(run_group.attrs)

    variables = []
    if "outputs" in run_group:
        for name in sorted(run_group["outputs"].keys()):
            values = np.asarray(run_group[f"outputs/{name}"][:], dtype=np.float64)
            variables.append(_summarize_array(name, values))

    final_state = _summarize_state_group(run_group, "final")
    initial_state = _summarize_state_group(run_group, "initial")

    event = container.provenance.get_latest_event_for_target(f"simulation/runs/{run_id}")
    event_dict = None
    if event is not None:
        event_timestamp = event.timestamp
        if event_timestamp is not None and hasattr(event_timestamp, "isoformat"):
            event_timestamp = event_timestamp.isoformat()
        event_dict = {
            "operation": event.operation,
            "timestamp": event_timestamp,
            "source": event.source,
            "params": event.params,
            "date_range": event.date_range,
            "records_count": event.records_count,
        }

    return RunReport(
        container_path=str(container.path),
        run_id=run_id,
        run_metadata=metadata,
        provenance_event=event_dict,
        variables=variables,
        final_state=final_state,
        initial_state=initial_state,
    )


def _summarize_state_group(run_group, which: str) -> list[RunStateStats]:
    group_path = f"state/{which}"
    if group_path not in run_group:
        return []
    state_group = run_group[group_path]
    stats = []
    for name in sorted(state_group.keys()):
        values = np.asarray(state_group[name][:], dtype=np.float64)
        stats.append(_summarize_state_array(name, values))
    return stats


def _summarize_array(name: str, values: np.ndarray) -> RunVariableStats:
    finite = np.isfinite(values)
    finite_fraction = float(finite.mean()) if values.size else 1.0
    if finite.any():
        valid = values[finite]
        minimum = float(np.min(valid))
        maximum = float(np.max(valid))
        mean = float(np.mean(valid))
    else:
        minimum = maximum = mean = None
    return RunVariableStats(
        name=name,
        shape=tuple(values.shape),
        finite_fraction=finite_fraction,
        minimum=minimum,
        maximum=maximum,
        mean=mean,
    )


def _summarize_state_array(name: str, values: np.ndarray) -> RunStateStats:
    finite = np.isfinite(values)
    finite_fraction = float(finite.mean()) if values.size else 1.0
    if finite.any():
        valid = values[finite]
        minimum = float(np.min(valid))
        maximum = float(np.max(valid))
        mean = float(np.mean(valid))
    else:
        minimum = maximum = mean = None
    return RunStateStats(
        state_name=name,
        finite_fraction=finite_fraction,
        minimum=minimum,
        maximum=maximum,
        mean=mean,
    )


def _json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_json_safe(v) for v in value]
    return value


_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>SWIM Run Report - {{ report.run_id }}</title>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
         max-width: 1100px; margin: 2em auto; padding: 0 1em; color: #24292e; }
  h1 { border-bottom: 2px solid #e1e4e8; padding-bottom: 0.3em; }
  h2 { border-bottom: 1px solid #e1e4e8; padding-bottom: 0.2em; margin-top: 1.5em; }
  .summary { background: #f6f8fa; border: 1px solid #e1e4e8; border-radius: 6px;
             padding: 1em; margin-bottom: 1.5em; }
  .summary dt { font-weight: 600; display: inline; }
  .summary dd { display: inline; margin-left: 0.3em; margin-right: 1.5em; }
  table { border-collapse: collapse; width: 100%; margin-bottom: 1em; }
  th, td { border: 1px solid #e1e4e8; padding: 6px 10px; text-align: right; }
  th { background: #f6f8fa; text-align: left; }
  td:first-child, th:first-child { text-align: left; }
  .good { color: #22863a; }
  .warn { color: #b08800; }
  footer { margin-top: 2em; padding-top: 1em; border-top: 1px solid #e1e4e8;
           font-size: 0.85em; color: #6a737d; }
</style>
</head>
<body>
<h1>SWIM Run Report</h1>

<div class="summary">
  <table>
    <tbody>
      <tr><th>Container</th><td>{{ report.container_path }}</td></tr>
      <tr><th>Run ID</th><td>{{ report.run_id }}</td></tr>
      <tr><th>Profile</th><td>{{ report.run_metadata.get('profile', 'unknown') }}</td></tr>
      <tr><th>Dates</th><td>{{ report.run_metadata.get('start_date', '?') }} to {{ report.run_metadata.get('end_date', '?') }}</td></tr>
      <tr><th>Fields</th><td>{{ report.run_metadata.get('field_count', '?') }}</td></tr>
      <tr><th>Days</th><td>{{ report.run_metadata.get('n_days', '?') }}</td></tr>
      <tr><th>Outputs finite</th><td class="{{ 'good' if report.all_outputs_finite else 'warn' }}">{{ report.all_outputs_finite }}</td></tr>
    </tbody>
  </table>
</div>

<h2>Outputs</h2>
<table>
  <thead>
    <tr><th>Variable</th><th>Shape</th><th>Finite Fraction</th><th>Min</th><th>Max</th><th>Mean</th></tr>
  </thead>
  <tbody>
  {% for variable in variables %}
    <tr>
      <td><strong>{{ variable.name }}</strong></td>
      <td>{{ variable.shape }}</td>
      <td>{{ "%.6f" | format(variable.finite_fraction) }}</td>
      <td>{{ variable.min }}</td>
      <td>{{ variable.max }}</td>
      <td>{{ variable.mean }}</td>
    </tr>
  {% endfor %}
  </tbody>
</table>

<h2>Final State</h2>
<table>
  <thead>
    <tr><th>State</th><th>Finite Fraction</th><th>Min</th><th>Max</th><th>Mean</th></tr>
  </thead>
  <tbody>
  {% for state in final_state %}
    <tr>
      <td><strong>{{ state.state_name }}</strong></td>
      <td>{{ "%.6f" | format(state.finite_fraction) }}</td>
      <td>{{ state.min }}</td>
      <td>{{ state.max }}</td>
      <td>{{ state.mean }}</td>
    </tr>
  {% endfor %}
  </tbody>
</table>

<footer>
  Generated {{ timestamp }} by swimrs run_report
</footer>
</body>
</html>
"""


def render_html_report(report: RunReport, output_path: str | Path) -> Path:
    """Render RunReport to a self-contained HTML file."""
    from jinja2 import Template

    output_path = Path(output_path)
    template = Template(_HTML_TEMPLATE)
    html = template.render(
        report=report,
        variables=[v.to_dict() for v in report.variables],
        final_state=[s.to_dict() for s in report.final_state],
        timestamp=datetime.now(UTC).isoformat(),
    )
    output_path.write_text(html)
    return output_path


def render_png_report(report: RunReport, output_path: str | Path) -> Path:
    """Render a compact run summary PNG."""
    import matplotlib.pyplot as plt

    output_path = Path(output_path)

    fig = plt.figure(figsize=(14, 6))
    fig.suptitle(
        f"Run {report.run_id}: {report.run_metadata.get('start_date', '?')}..{report.run_metadata.get('end_date', '?')}",
        fontsize=13,
        fontweight="bold",
    )

    ax1 = fig.add_subplot(1, 2, 1)
    if report.variables:
        labels = [v.name for v in report.variables]
        means = [0.0 if v.mean is None else v.mean for v in report.variables]
        ax1.barh(labels, means, color="#4a90d9")
        ax1.set_xlabel("Mean")
    ax1.set_title("Output Means")

    ax2 = fig.add_subplot(1, 2, 2)
    if report.variables:
        labels = [v.name for v in report.variables]
        finites = [100.0 * v.finite_fraction for v in report.variables]
        ax2.barh(labels, finites, color="#22863a")
        ax2.set_xlim(0, 100)
        ax2.set_xlabel("% Finite")
    ax2.set_title("Output Completeness")

    plt.tight_layout()
    fig.savefig(str(output_path), dpi=150, bbox_inches="tight")
    plt.close(fig)
    return output_path
