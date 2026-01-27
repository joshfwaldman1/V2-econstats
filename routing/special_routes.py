"""
Special Routes - Fed SEP, Recession Scorecard, CAPE, Polymarket.

Handles queries that need special data beyond standard FRED series.
"""

from typing import Optional, Dict, Any
from dataclasses import dataclass


@dataclass
class SpecialRouteResult:
    """Result from a special route check."""
    matched: bool = False
    route_type: str = ''
    series: list = None
    show_yoy: bool = False
    extra_data: dict = None  # For special HTML boxes

    def __post_init__(self):
        if self.series is None:
            self.series = []
        if self.extra_data is None:
            self.extra_data = {}


class SpecialRouter:
    """Handles special query routes that need custom handling."""

    def __init__(self):
        self._fed_sep = None
        self._recession = None
        self._polymarket = None
        self._health_check = None
        self._shiller = None
        self._load_modules()

    def _load_modules(self):
        """Lazy load special modules."""
        # Fed SEP
        try:
            from agents.fed_sep import (
                is_fed_related_query, is_sep_query,
                get_fed_guidance_for_query, get_sep_data, get_current_fed_funds_rate
            )
            self._fed_sep = {
                'is_fed_query': is_fed_related_query,
                'is_sep_query': is_sep_query,
                'get_guidance': get_fed_guidance_for_query,
                'get_sep_data': get_sep_data,
                'get_rate': get_current_fed_funds_rate,
            }
            print("[SpecialRoutes] Fed SEP: available")
        except Exception as e:
            print(f"[SpecialRoutes] Fed SEP: not available - {e}")

        # Recession scorecard
        try:
            from agents.recession_scorecard import (
                is_recession_query, build_recession_scorecard, format_scorecard_for_display
            )
            self._recession = {
                'is_query': is_recession_query,
                'build_scorecard': build_recession_scorecard,
                'format_display': format_scorecard_for_display,
            }
            print("[SpecialRoutes] Recession scorecard: available")
        except Exception as e:
            print(f"[SpecialRoutes] Recession scorecard: not available - {e}")

        # Polymarket
        try:
            from agents.polymarket import find_relevant_predictions, format_predictions_box
            self._polymarket = {
                'find_predictions': find_relevant_predictions,
                'format_box': format_predictions_box,
            }
            print("[SpecialRoutes] Polymarket: available")
        except Exception as e:
            print(f"[SpecialRoutes] Polymarket: not available - {e}")

        # Health check indicators
        try:
            from core.health_check_indicators import (
                is_health_check_query, detect_health_check_entity, get_health_check_config
            )
            self._health_check = {
                'is_query': is_health_check_query,
                'detect_entity': detect_health_check_entity,
                'get_config': get_health_check_config,
            }
            print("[SpecialRoutes] Health check: available")
        except Exception as e:
            print(f"[SpecialRoutes] Health check: not available - {e}")

        # Shiller CAPE data
        try:
            from agents.shiller import (
                is_valuation_query, get_current_cape, get_bubble_comparison_data, get_cape_series
            )
            self._shiller = {
                'is_query': is_valuation_query,
                'get_current': get_current_cape,
                'get_bubble_data': get_bubble_comparison_data,
                'get_series': get_cape_series,
            }
            print("[SpecialRoutes] Shiller CAPE: available")
        except Exception as e:
            print(f"[SpecialRoutes] Shiller CAPE: not available - {e}")

    def check(self, query: str) -> Optional[SpecialRouteResult]:
        """
        Check if query matches any special route.

        Returns SpecialRouteResult if matched, None otherwise.
        """
        # Check Fed SEP
        if self._fed_sep and self._fed_sep['is_fed_query'](query):
            return self._handle_fed_query(query)

        # Check recession scorecard
        if self._recession and self._recession['is_query'](query):
            return self._handle_recession_query(query)

        # Check health check
        if self._health_check and self._health_check['is_query'](query):
            return self._handle_health_check_query(query)

        # Check CAPE/valuation/bubble queries
        if self._shiller and self._shiller['is_query'](query):
            return self._handle_cape_query(query)

        return None

    def _handle_fed_query(self, query: str) -> SpecialRouteResult:
        """Handle Fed-related queries."""
        guidance = self._fed_sep['get_guidance'](query)

        result = SpecialRouteResult(
            matched=True,
            route_type='fed_sep',
            series=guidance.get('series', ['FEDFUNDS', 'DGS10', 'DGS2']) if guidance else ['FEDFUNDS', 'DGS10'],
            show_yoy=False,
        )

        # Get SEP data for special display
        if self._fed_sep['is_sep_query'](query):
            try:
                sep_data = self._fed_sep['get_sep_data']()
                if sep_data:
                    result.extra_data['fed_sep'] = sep_data
                    result.extra_data['fed_sep_html'] = self._format_fed_sep_html(sep_data)
            except:
                pass

        if guidance:
            result.extra_data['fed_guidance'] = guidance

        return result

    def _handle_recession_query(self, query: str) -> SpecialRouteResult:
        """Handle recession queries."""
        result = SpecialRouteResult(
            matched=True,
            route_type='recession',
            series=['SAHMREALTIME', 'T10Y2Y', 'UNRATE', 'ICSA'],
            show_yoy=False,
        )

        # Build scorecard
        try:
            scorecard = self._recession['build_scorecard']()
            if scorecard:
                result.extra_data['recession_scorecard'] = scorecard
                result.extra_data['recession_html'] = self._recession['format_display'](scorecard)
        except:
            pass

        return result

    def _handle_health_check_query(self, query: str) -> SpecialRouteResult:
        """Handle health check queries (megacap, labor market, etc.)."""
        entity = self._health_check['detect_entity'](query)
        if not entity:
            return None

        config = self._health_check['get_config'](entity)
        if not config:
            return None

        return SpecialRouteResult(
            matched=True,
            route_type='health_check',
            series=config.get('series', []),
            show_yoy=config.get('show_yoy', False),
            extra_data={'entity': entity, 'config': config}
        )

    def _handle_cape_query(self, query: str) -> SpecialRouteResult:
        """Handle CAPE/valuation/bubble queries."""
        result = SpecialRouteResult(
            matched=True,
            route_type='cape',
            # Include S&P 500 and VIX alongside CAPE for market context
            series=['SP500', 'VIXCLS'],
            show_yoy=False,
        )

        # Get CAPE data and format HTML box
        try:
            bubble_data = self._shiller['get_bubble_data']()
            if bubble_data:
                result.extra_data['cape_data'] = bubble_data
                result.extra_data['cape_html'] = self._format_cape_html(bubble_data)
        except Exception as e:
            print(f"[SpecialRoutes] Error getting CAPE data: {e}")

        return result

    def _format_cape_html(self, bubble_data: dict) -> str:
        """Format CAPE valuation data as HTML box."""
        if not bubble_data:
            return ''

        current = bubble_data.get('current', {})
        cape_value = current.get('current_value', 'N/A')
        percentile = current.get('percentile', 0)
        interpretation = current.get('interpretation', '')
        cape_date = current.get('current_date', '')

        dot_com = bubble_data.get('dot_com_comparison', {})
        dot_com_peak = dot_com.get('peak_cape', 44.2)
        vs_dot_com = dot_com.get('current_vs_peak_pct', 0)

        vs_avg = current.get('vs_average', {})
        long_term_avg = vs_avg.get('long_term_avg', 17)
        premium_pct = vs_avg.get('premium_pct', 0)

        summary = bubble_data.get('summary', '')

        # Color coding based on percentile
        if percentile >= 90:
            color_class = 'red'
            bg_color = 'bg-red-50'
            border_color = 'border-red-200'
            text_color = 'text-red-800'
            value_color = 'text-red-600'
        elif percentile >= 70:
            color_class = 'amber'
            bg_color = 'bg-amber-50'
            border_color = 'border-amber-200'
            text_color = 'text-amber-800'
            value_color = 'text-amber-600'
        else:
            color_class = 'green'
            bg_color = 'bg-green-50'
            border_color = 'border-green-200'
            text_color = 'text-green-800'
            value_color = 'text-green-600'

        html = f'''
        <div class="{bg_color} border {border_color} rounded-xl p-4 mb-4">
            <div class="flex items-center gap-2 mb-3">
                <svg class="w-5 h-5 {text_color}" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                          d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"/>
                </svg>
                <span class="font-semibold {text_color}">Shiller CAPE Valuation ({cape_date})</span>
            </div>

            <div class="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm mb-3">
                <div class="bg-white rounded-lg p-3">
                    <div class="text-xs text-slate-500">Current CAPE</div>
                    <div class="text-xl font-bold {value_color}">{cape_value}</div>
                    <div class="text-xs text-slate-400">{percentile:.0f}th percentile</div>
                </div>
                <div class="bg-white rounded-lg p-3">
                    <div class="text-xs text-slate-500">Long-term Avg</div>
                    <div class="text-xl font-bold text-slate-700">{long_term_avg}</div>
                    <div class="text-xs text-slate-400">since 1881</div>
                </div>
                <div class="bg-white rounded-lg p-3">
                    <div class="text-xs text-slate-500">vs Average</div>
                    <div class="text-xl font-bold {value_color}">{premium_pct:+.0f}%</div>
                    <div class="text-xs text-slate-400">premium</div>
                </div>
                <div class="bg-white rounded-lg p-3">
                    <div class="text-xs text-slate-500">vs Dot-com Peak</div>
                    <div class="text-xl font-bold text-slate-700">{vs_dot_com:+.0f}%</div>
                    <div class="text-xs text-slate-400">peak was {dot_com_peak}</div>
                </div>
            </div>

            <p class="text-sm {text_color}">{summary}</p>
            <p class="text-xs text-slate-500 mt-2">Source: Robert Shiller, Yale University</p>
        </div>
        '''
        return html

    def _format_fed_sep_html(self, sep_data: dict) -> str:
        """Format Fed SEP data as HTML box."""
        if not sep_data:
            return ''

        projections = sep_data.get('projections', {})
        meeting_date = sep_data.get('meeting_date', 'Latest')

        html = f'''
        <div class="bg-blue-50 border border-blue-200 rounded-xl p-4 mb-4">
            <div class="flex items-center gap-2 mb-3">
                <svg class="w-5 h-5 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                          d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"/>
                </svg>
                <span class="font-semibold text-blue-800">Fed Projections ({meeting_date})</span>
            </div>
            <div class="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
        '''

        for var, data in projections.items():
            if isinstance(data, dict) and 'median' in data:
                html += f'''
                <div class="bg-white rounded-lg p-2">
                    <div class="text-xs text-slate-500">{var}</div>
                    <div class="font-semibold text-slate-800">{data['median']}</div>
                </div>
                '''

        html += '</div></div>'
        return html

    def get_polymarket_predictions(self, query: str) -> Optional[str]:
        """Get Polymarket predictions HTML for a query."""
        if not self._polymarket:
            return None

        try:
            predictions = self._polymarket['find_predictions'](query)
            if predictions:
                return self._polymarket['format_box'](predictions)
        except:
            pass

        return None

    @property
    def fed_available(self) -> bool:
        return self._fed_sep is not None

    @property
    def recession_available(self) -> bool:
        return self._recession is not None

    @property
    def polymarket_available(self) -> bool:
        return self._polymarket is not None

    @property
    def shiller_available(self) -> bool:
        return self._shiller is not None


# Global instance
special_router = SpecialRouter()
