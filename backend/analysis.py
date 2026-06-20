"""Data processing: CSV cleaning, date detection, anomaly detection, metric calculation."""
import re
from typing import List, Optional

import numpy as np
import pandas as pd

from models import Anomaly, DataQualityIssue, DataQualityReport, MetricConfig, MetricSummary, SuggestedMetricConfig

# Common date formats we try, in order of specificity
_DATE_FORMATS = [
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%d-%m-%Y",
    "%d/%m/%Y",
    "%m-%d-%Y",
    "%m/%d/%Y",
    "%Y-%m-%d %H:%M:%S",
    "%d %b %Y",
    "%d %B %Y",
    "%b %d %Y",
    "%B %d %Y",
]

_DATE_HINT_PATTERN = re.compile(
    r"\d{1,4}[-/\s]\d{1,2}[-/\s]\d{1,4}|\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b",
    re.IGNORECASE,
)


def _detect_date_column(series: pd.Series) -> tuple[bool, list[str], int]:
    """Return (is_date_column, formats_matched, sample_count).

    A column is considered a date column if at least 50% of non-empty string values look
    like dates by a regex hint AND parse cleanly under at least one known format. We
    also collect every format that successfully parses any value so we can detect
    inconsistent date formats.
    """
    non_empty = [str(v).strip() for v in series.dropna().tolist() if str(v).strip() and str(v).strip().lower() != 'nan']
    if len(non_empty) < 2:
        return False, [], 0

    hint_matches = sum(1 for v in non_empty if _DATE_HINT_PATTERN.search(v))
    if hint_matches / len(non_empty) < 0.5:
        return False, [], 0

    formats_matched: set[str] = set()
    parsed_count = 0
    for val in non_empty:
        for fmt in _DATE_FORMATS:
            try:
                pd.to_datetime(val, format=fmt)
                formats_matched.add(fmt)
                parsed_count += 1
                break
            except (ValueError, TypeError):
                continue

    is_date = parsed_count / len(non_empty) >= 0.5
    return is_date, sorted(formats_matched), len(non_empty)


def clean_and_analyze_csv(raw_data: List[dict]) -> DataQualityReport:
    """Clean CSV data and generate a quality report."""
    df = pd.DataFrame(raw_data)
    original_data = raw_data.copy()
    issues: List[DataQualityIssue] = []
    score = 100

    # Remove completely empty rows
    initial_rows = len(df)
    df = df.dropna(how='all')
    rows_removed = initial_rows - len(df)
    if rows_removed > 0:
        issues.append(DataQualityIssue(type="warning", message=f"Removed {rows_removed} completely empty rows"))
        score -= 5

    # Remove completely empty columns
    df = df.dropna(axis=1, how='all')

    # Trim whitespace from string columns
    for col in df.select_dtypes(include=['object']).columns:
        df[col] = df[col].astype(str).str.strip()

    # Detect duplicates (report only, don't auto-remove)
    duplicates = int(df.duplicated().sum())
    if duplicates > 0:
        issues.append(DataQualityIssue(type="warning", message=f"Found {duplicates} duplicate rows (not auto-removed)"))
        score -= 10

    # Detect date columns FIRST so they don't get classified as labels
    date_columns: List[str] = []
    for col in df.columns:
        is_date, formats, _ = _detect_date_column(df[col])
        if is_date:
            date_columns.append(col)
            if len(formats) > 1:
                issues.append(DataQualityIssue(
                    type="error",
                    message=f"Column '{col}' has {len(formats)} different date formats — please standardize",
                ))
                score -= 8
            else:
                issues.append(DataQualityIssue(
                    type="success",
                    message=f"Column '{col}' uses a consistent date format",
                ))

    # Detect numeric vs label columns
    numeric_columns: List[str] = []
    label_columns: List[str] = []

    for col in df.columns:
        if col in date_columns:
            continue
        try:
            test_series = df[col].astype(str).str.replace('$', '', regex=False).str.replace(',', '', regex=False)
            pd.to_numeric(test_series, errors='raise')
            df[col] = pd.to_numeric(
                df[col].astype(str).str.replace('$', '', regex=False).str.replace(',', '', regex=False),
                errors='coerce',
            )
            numeric_columns.append(col)
        except (ValueError, TypeError):
            label_columns.append(col)

    # Check for missing values in numeric columns
    for col in numeric_columns:
        missing = int(df[col].isna().sum())
        if missing > 0:
            issues.append(DataQualityIssue(type="error", message=f"Column '{col}' has {missing} missing numeric values"))
            score -= 15

    # Success messages
    if rows_removed == 0:
        issues.append(DataQualityIssue(type="success", message="No empty rows found"))
    if duplicates == 0:
        issues.append(DataQualityIssue(type="success", message="No duplicate rows found"))
    if len(numeric_columns) > 0:
        issues.append(DataQualityIssue(type="success", message=f"All {len(numeric_columns)} numeric columns valid"))

    score = max(0, score)

    return DataQualityReport(
        score=score,
        issues=issues,
        rows_removed=rows_removed,
        duplicates_found=duplicates,
        cleaned_data=df.to_dict('records'),
        original_data=original_data,
        numeric_columns=numeric_columns,
        label_columns=label_columns,
        date_columns=date_columns,
    )


def detect_anomalies(df: pd.DataFrame, numeric_columns: List[str], label_columns: List[str]) -> List[Anomaly]:
    """Flag values with |z-score| >= 1.8 (>= 2.2 = Critical)."""
    anomalies: List[Anomaly] = []

    for col in numeric_columns:
        values = df[col].dropna()
        if len(values) < 3:
            continue

        mean = values.mean()
        std = values.std()
        if std == 0:
            continue

        for idx, val in enumerate(df[col]):
            if pd.isna(val):
                continue
            z_score = abs((val - mean) / std)
            if z_score >= 1.8:
                label_val = df.iloc[idx][label_columns[0]] if label_columns else f"Row {idx}"
                severity = "Critical" if z_score >= 2.2 else "Warning"
                anomalies.append(Anomaly(
                    metric=col,
                    value=float(val),
                    expected_range=f"{mean - 2*std:.1f} - {mean + 2*std:.1f}",
                    z_score=float(z_score),
                    severity=severity,
                    row_index=idx,
                    label=str(label_val),
                ))

    anomalies.sort(key=lambda a: (0 if a.severity == "Critical" else 1, -a.z_score))
    return anomalies


def calculate_metrics(
    df: pd.DataFrame,
    numeric_columns: List[str],
    label_columns: List[str],
    anomalies: List[Anomaly],
    metric_configs: Optional[List[MetricConfig]] = None,
) -> List[MetricSummary]:
    """Per-metric summary with sparkline values, MoM change, and trend.

    If `metric_configs` is provided, only enabled configs are computed; each metric's
    headline `latest_value` reflects the chosen calculation (sum/mean/min/max/count/
    growth/latest). The raw value series is still preserved in `values` for sparkline
    rendering on the frontend.
    """
    metrics: List[MetricSummary] = []

    if label_columns:
        labels = df[label_columns[0]].astype(str).tolist()
    else:
        labels = [f"Row {i}" for i in range(len(df))]

    # Resolve which (column, display_name, calculation) tuples to emit
    if metric_configs:
        items = [(c.column, c.display_name or c.column, c.calculation) for c in metric_configs if c.enabled]
    else:
        items = [(c, c, 'latest') for c in numeric_columns]

    for column, display_name, calculation in items:
        if column not in df.columns:
            continue
        values = df[column].fillna(0).tolist()
        if not values:
            continue

        headline = compute_headline_value(values, calculation)

        mom_change = None
        if len(values) >= 2 and values[-2] != 0:
            mom_change = ((values[-1] - values[-2]) / values[-2]) * 100

        if len(values) >= 2:
            mean_v = np.mean(values)
            trend_slope = np.mean(np.diff(values))
            if abs(trend_slope) < 0.01 * abs(mean_v):
                trend, trend_percent = "flat", 0
            elif trend_slope > 0:
                trend = "up"
                trend_percent = (trend_slope / mean_v) * 100 if mean_v != 0 else 0
            else:
                trend = "down"
                trend_percent = (trend_slope / mean_v) * 100 if mean_v != 0 else 0
        else:
            trend, trend_percent = "flat", 0

        metric_anomalies = [a for a in anomalies if a.metric == column]

        metrics.append(MetricSummary(
            name=display_name,
            column=column,
            calculation=calculation,
            latest_value=float(headline),
            mom_change=float(mom_change) if mom_change is not None else None,
            trend=trend,
            trend_percent=float(trend_percent),
            values=[float(v) for v in values],
            labels=labels,
            mean=float(np.mean(values)),
            std_dev=float(np.std(values)),
            anomalies=metric_anomalies,
        ))

    return metrics


# ============================================================================
# Smart metric suggestions
# ============================================================================

_KW_AVERAGE = {
    'score', 'rate', 'percent', 'percentage', 'ratio', 'index', 'rating',
    'csat', 'nps', 'dsat', 'satisfaction', 'churn', 'loss', 'drop', 'error',
    'cac', 'aov', 'ltv', 'arpu', 'price', 'cost', 'unit', 'average', 'avg',
    'mean', 'median', 'efficiency',
}
_KW_SUM = {
    'revenue', 'sales', 'amount', 'total', 'sum', 'spend', 'income',
    'orders', 'customers', 'users', 'visits', 'clicks', 'transactions',
    'tickets', 'requests', 'signups', 'conversions', 'sessions', 'pageviews',
}
_KW_COUNT = {'id', 'count'}


def suggest_calculation(column_name: str, sample_values: List[float]) -> tuple[str, str]:
    """Heuristically pick a default calculation + a short user-facing rationale."""
    name = column_name.lower()
    tokens = set(re.split(r'[\s_\-./]+', name))

    # Boolean-ish (0/1) columns → sum (counts occurrences)
    sample = [v for v in sample_values[:200] if v is not None]
    if sample:
        unique = set(sample)
        if len(unique) <= 2 and unique.issubset({0, 1, 0.0, 1.0}):
            return 'sum', 'Looks boolean (0/1) — count occurrences'

    # ID-only columns are usually unique-per-row → count
    if 'id' in tokens or name.endswith('_id') or name.endswith(' id'):
        return 'count', 'ID column — count distinct rows'

    if tokens & _KW_AVERAGE:
        return 'mean', 'Rate/score-like — average across rows'

    if tokens & _KW_SUM:
        return 'sum', 'Aggregate-like — sum across rows'

    # Many rows + no obvious keyword → fall back to mean (safer than latest when
    # each row is a discrete event rather than a time-series point)
    if len(sample_values) > 100:
        return 'mean', 'Many rows — average is usually meaningful'

    return 'latest', 'Looks time-series — show latest period'


def suggest_display_name(column_name: str) -> str:
    """Turn a raw column header into a readable label.

    'monthly_revenue' → 'Monthly Revenue'; 'CAC' / 'NPS' preserved as acronyms.
    """
    cleaned = re.sub(r'[_\-]+', ' ', column_name).strip()
    parts = cleaned.split()
    out = []
    for p in parts:
        # Preserve short ALL-CAPS tokens (likely acronyms)
        if p.isupper() and len(p) <= 5:
            out.append(p)
        else:
            out.append(p.capitalize())
    return ' '.join(out) if out else column_name


def compute_headline_value(values: List[float], calculation: str) -> float:
    """Reduce a value series to a single headline number using the chosen calculation."""
    valid = [v for v in values if v is not None and not (isinstance(v, float) and np.isnan(v))]
    if not valid:
        return 0.0

    if calculation == 'sum':
        return float(sum(valid))
    if calculation == 'mean':
        return float(sum(valid) / len(valid))
    if calculation == 'min':
        return float(min(valid))
    if calculation == 'max':
        return float(max(valid))
    if calculation == 'count':
        return float(len(valid))
    if calculation == 'growth':
        if len(valid) < 2 or valid[0] == 0:
            return 0.0
        return float(((valid[-1] - valid[0]) / valid[0]) * 100)
    # default: 'latest'
    return float(valid[-1])


def build_suggested_metric_configs(
    df: pd.DataFrame,
    numeric_columns: List[str],
) -> List[SuggestedMetricConfig]:
    """Generate per-column smart defaults the frontend can pre-fill the form with."""
    suggestions: List[SuggestedMetricConfig] = []
    for col in numeric_columns:
        values = df[col].dropna().tolist() if col in df.columns else []
        calc, rationale = suggest_calculation(col, values)
        suggestions.append(SuggestedMetricConfig(
            column=col,
            suggested_display_name=suggest_display_name(col),
            suggested_calculation=calc,
            rationale=rationale,
        ))
    return suggestions
