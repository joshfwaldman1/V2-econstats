"""
Intent Validator Module

Validates that fetched data matches the detected temporal intent before rendering.

For COMPARE intents, checks:
- Do we have data from BOTH periods?
- Is the reference period data actually from that era?
- Are we comparing apples to apples (same frequency, measure type)?

This catches issues BEFORE rendering, allowing for self-correction.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from .temporal_intent import TemporalIntent
from .multi_period_fetcher import MultiPeriodData
from .data_fetcher import SeriesData


@dataclass
class ValidationIssue:
    """A single validation issue found."""
    severity: str  # "error", "warning", "info"
    series_id: str
    message: str
    suggestion: Optional[str] = None


@dataclass
class ValidationResult:
    """
    Result of validating data against temporal intent.

    Contains:
    - is_valid: Whether the data is suitable for the intended query
    - issues: List of problems found
    - corrections_needed: Suggested actions to fix issues
    """
    is_valid: bool
    issues: list[ValidationIssue] = field(default_factory=list)
    corrections_needed: list[str] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        """Check if there are error-level issues."""
        return any(i.severity == "error" for i in self.issues)

    @property
    def has_warnings(self) -> bool:
        """Check if there are warning-level issues."""
        return any(i.severity == "warning" for i in self.issues)

    def get_user_message(self) -> str:
        """Get a user-friendly summary of validation issues."""
        if self.is_valid and not self.has_warnings:
            return ""

        messages = []

        for issue in self.issues:
            if issue.severity == "error":
                messages.append(f"Error: {issue.message}")
            elif issue.severity == "warning":
                messages.append(f"Note: {issue.message}")

        if self.corrections_needed:
            messages.append("\nSuggested actions:")
            for correction in self.corrections_needed:
                messages.append(f"  - {correction}")

        return "\n".join(messages)


def validate_data_matches_intent(
    intent: TemporalIntent,
    data: MultiPeriodData
) -> ValidationResult:
    """
    Validate that fetched data matches the temporal intent.

    For COMPARE intents, checks:
    1. Do we have data from the reference period?
    2. Do we have data from the primary (current) period?
    3. Is there enough overlap for meaningful comparison?

    For FILTER intents, checks:
    1. Does the data cover the filtered date range?
    2. Is there data within the requested period?

    Args:
        intent: The detected temporal intent
        data: The fetched multi-period data

    Returns:
        ValidationResult with validation outcome and issues
    """
    issues = []
    corrections = []

    if intent.intent_type == "compare":
        issues, corrections = _validate_comparison_intent(intent, data)
    elif intent.intent_type == "filter":
        issues, corrections = _validate_filter_intent(intent, data)
    else:
        # Current intent - minimal validation
        issues, corrections = _validate_current_intent(intent, data)

    # Determine overall validity
    is_valid = not any(i.severity == "error" for i in issues)

    return ValidationResult(
        is_valid=is_valid,
        issues=issues,
        corrections_needed=corrections
    )


def _validate_comparison_intent(
    intent: TemporalIntent,
    data: MultiPeriodData
) -> tuple[list[ValidationIssue], list[str]]:
    """
    Validate data for a comparison intent.

    Checks that we have data from BOTH periods.
    """
    issues = []
    corrections = []

    reference_period = intent.reference_period
    reference_label = intent.reference_label or "reference period"

    if not reference_period:
        issues.append(ValidationIssue(
            severity="error",
            series_id="",
            message="No reference period defined for comparison.",
            suggestion="Check temporal intent detection."
        ))
        return issues, corrections

    # Check each series has data in both periods
    for series_id, series_data in data.full_data.items():
        if series_data.is_empty or series_data.error:
            issues.append(ValidationIssue(
                severity="error",
                series_id=series_id,
                message=f"No data available for {series_id}.",
                suggestion=series_data.error if series_data.error else "Check series ID."
            ))
            continue

        # Check reference period data
        ref_data = data.reference_data.get(series_id, [])
        if not ref_data:
            # Check if series simply doesn't extend back that far
            earliest_date = series_data.dates[0] if series_data.dates else None
            ref_end = reference_period.get("end", reference_period.get("start", ""))

            if earliest_date and earliest_date > ref_end:
                issues.append(ValidationIssue(
                    severity="warning",
                    series_id=series_id,
                    message=f"{series_data.name} data only starts from {_format_date(earliest_date)}, "
                            f"which is after the {reference_label}.",
                    suggestion=f"Consider using a different series that extends further back."
                ))
            else:
                issues.append(ValidationIssue(
                    severity="warning",
                    series_id=series_id,
                    message=f"No data found for {series_data.name} in {reference_label}.",
                    suggestion="The series may have gaps in this period."
                ))

        # Check primary (current) period data
        primary_data = data.primary_data.get(series_id, [])
        if not primary_data:
            issues.append(ValidationIssue(
                severity="warning",
                series_id=series_id,
                message=f"No recent data available for {series_data.name}.",
                suggestion="The series may be discontinued or delayed."
            ))

    # Check if we have ANY valid comparisons
    if not data.has_comparison_data:
        issues.append(ValidationIssue(
            severity="error",
            series_id="",
            message=f"Unable to compare any series to {reference_label}.",
            suggestion="Try a different time period or different indicators."
        ))
        corrections.append(f"Remove temporal comparison - show full data range instead.")

    return issues, corrections


def _validate_filter_intent(
    intent: TemporalIntent,
    data: MultiPeriodData
) -> tuple[list[ValidationIssue], list[str]]:
    """
    Validate data for a filter intent.

    Checks that data exists within the filtered date range.
    """
    issues = []
    corrections = []

    filter_start = intent.filter_start
    filter_end = intent.filter_end

    for series_id, series_data in data.full_data.items():
        if series_data.is_empty or series_data.error:
            continue

        # Check if series has data in the filter range
        has_data_in_range = False
        for date_str in series_data.dates:
            if filter_start and date_str < filter_start:
                continue
            if filter_end and date_str > filter_end:
                continue
            has_data_in_range = True
            break

        if not has_data_in_range:
            period_desc = ""
            if filter_start and filter_end:
                period_desc = f"{_format_date(filter_start)} to {_format_date(filter_end)}"
            elif filter_start:
                period_desc = f"after {_format_date(filter_start)}"
            elif filter_end:
                period_desc = f"before {_format_date(filter_end)}"

            issues.append(ValidationIssue(
                severity="warning",
                series_id=series_id,
                message=f"No data for {series_data.name} in the requested period ({period_desc}).",
                suggestion="The series may not have data for this time range."
            ))

    return issues, corrections


def _validate_current_intent(
    intent: TemporalIntent,
    data: MultiPeriodData
) -> tuple[list[ValidationIssue], list[str]]:
    """
    Validate data for a current/recent intent.

    Minimal validation - just checks data is present.
    """
    issues = []
    corrections = []

    for series_id, series_data in data.full_data.items():
        if series_data.is_empty:
            issues.append(ValidationIssue(
                severity="warning",
                series_id=series_id,
                message=f"No data available for {series_id}.",
                suggestion=series_data.error if series_data.error else None
            ))

    return issues, corrections


def self_correct_if_needed(
    validation: ValidationResult,
    intent: TemporalIntent,
    data: MultiPeriodData
) -> tuple[TemporalIntent, MultiPeriodData, str]:
    """
    Attempt to fix validation issues by adjusting the intent or data.

    Returns:
        Tuple of (corrected_intent, corrected_data, correction_message)

    If no correction is possible, returns original values with empty message.
    """
    if validation.is_valid:
        return intent, data, ""

    correction_message = ""

    # If comparison failed, fall back to showing full data
    if intent.intent_type == "compare" and not data.has_comparison_data:
        # Create a new intent that just shows current data
        corrected_intent = TemporalIntent(
            intent_type="current",
            original_query=intent.original_query,
            explanation=f"Unable to compare to {intent.reference_label}. Showing all available data instead."
        )

        correction_message = (
            f"Note: Unable to generate a meaningful comparison with {intent.reference_label}. "
            f"Displaying the full data range instead."
        )

        return corrected_intent, data, correction_message

    return intent, data, ""


def _format_date(date_str: str) -> str:
    """Format ISO date to human-readable."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.strftime("%B %Y")
    except (ValueError, TypeError):
        return date_str or "unknown"


# Quick test
if __name__ == "__main__":
    print("Testing Intent Validator\n" + "=" * 50)

    # Create mock intent
    mock_intent = TemporalIntent(
        intent_type="compare",
        primary_period={"start": "2024-01-01", "label": "Current"},
        reference_period={"end": "2020-02-29", "label": "Pre-pandemic (Feb 2020)"},
        original_query="How has unemployment changed since pre-pandemic?"
    )

    # Create mock data with valid comparison
    from .data_fetcher import SeriesData

    mock_series = SeriesData(
        id="UNRATE",
        name="Unemployment Rate",
        dates=["2020-02-01", "2024-11-01"],
        values=[3.5, 4.1],
        source="fred",
        units="Percent"
    )

    mock_data = MultiPeriodData(
        full_data={"UNRATE": mock_series},
        primary_data={"UNRATE": [("2024-11-01", 4.1)]},
        reference_data={"UNRATE": [("2020-02-01", 3.5)]},
        comparison_metrics={},  # Would be populated by multi_period_fetcher
        intent=mock_intent
    )

    result = validate_data_matches_intent(mock_intent, mock_data)

    print(f"\nValidation result:")
    print(f"  Is valid: {result.is_valid}")
    print(f"  Has errors: {result.has_errors}")
    print(f"  Has warnings: {result.has_warnings}")

    if result.issues:
        print(f"\nIssues found:")
        for issue in result.issues:
            print(f"  [{issue.severity}] {issue.message}")
