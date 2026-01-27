"""
Provider Health Tracking Module for AI Translator.
Tracks success/failure rates and response times for intelligent provider selection.
"""
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, TYPE_CHECKING
from dataclasses import dataclass, field, asdict

if TYPE_CHECKING:
    from config import Config


@dataclass
class ProviderStats:
    """Statistics for a single provider."""
    success_count: int = 0
    fail_count: int = 0
    total_response_time_ms: int = 0
    last_failure: Optional[str] = None  # ISO format datetime
    consecutive_failures: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ProviderStats':
        """Create from dictionary."""
        return cls(
            success_count=data.get('success_count', 0),
            fail_count=data.get('fail_count', 0),
            total_response_time_ms=data.get('total_response_time_ms', 0),
            last_failure=data.get('last_failure'),
            consecutive_failures=data.get('consecutive_failures', 0)
        )


class ProviderHealthManager:
    """
    Manages provider health tracking for intelligent fallback selection.

    Features:
    - Tracks success rate, response time, and consecutive failures
    - Calculates priority scores for provider ordering
    - Implements soft circuit breaker for failing providers
    - Provides adaptive timeouts based on historical performance

    Usage:
        health = ProviderHealthManager(config)

        # Before calling API
        sorted_providers = health.get_priority_sorted_providers(available_providers)
        timeout = health.get_adaptive_timeout(provider)

        # After API call
        health.record_success(provider, response_time_ms)
        # or
        health.record_failure(provider)
    """

    # Circuit breaker thresholds
    CIRCUIT_BREAKER_THRESHOLD = 3  # consecutive failures to trigger
    CIRCUIT_BREAKER_RECOVERY = {
        3: 60,      # 3 failures -> 1 minute skip
        5: 300,     # 5 failures -> 5 minutes skip
        10: 1800,   # 10+ failures -> 30 minutes skip
    }

    # Timeout settings (in seconds)
    DEFAULT_TIMEOUT = 10.0
    MIN_TIMEOUT = 3.0
    MAX_TIMEOUT = 30.0
    TIMEOUT_MULTIPLIER = 2.5  # timeout = avg_time * multiplier + buffer
    TIMEOUT_BUFFER_MS = 1000  # extra buffer in ms

    # Scoring weights
    WEIGHT_SUCCESS_RATE = 0.4
    WEIGHT_RESPONSE_TIME = 0.3
    WEIGHT_RECENT_STABILITY = 0.3

    # Normalization constants
    MAX_ACCEPTABLE_RESPONSE_TIME_MS = 10000  # 10 seconds

    def __init__(self, config: 'Config') -> None:
        """
        Initialize ProviderHealthManager.

        Args:
            config: Config instance for persistence
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        self._health_data: Dict[str, ProviderStats] = {}
        self._load_health_data()

    def _load_health_data(self) -> None:
        """Load health data from config."""
        try:
            raw_data = self.config.get('provider_health', {})
            for provider, stats_dict in raw_data.items():
                self._health_data[provider] = ProviderStats.from_dict(stats_dict)
            self.logger.debug(f"Loaded health data for {len(self._health_data)} providers")
        except Exception as e:
            self.logger.error(f"Error loading health data: {e}")
            self._health_data = {}

    def _save_health_data(self) -> None:
        """Save health data to config."""
        try:
            raw_data = {
                provider: stats.to_dict()
                for provider, stats in self._health_data.items()
            }
            # config.set() already calls save()
            self.config.set('provider_health', raw_data)
        except Exception as e:
            self.logger.error(f"Error saving health data: {e}")

    def _get_stats(self, provider: str) -> ProviderStats:
        """Get or create stats for a provider."""
        if provider not in self._health_data:
            self._health_data[provider] = ProviderStats()
        return self._health_data[provider]

    def record_success(self, provider: str, response_time_ms: int) -> None:
        """
        Record a successful API call.

        Args:
            provider: Provider identifier (e.g., 'google', 'openai')
            response_time_ms: Response time in milliseconds
        """
        stats = self._get_stats(provider)
        stats.success_count += 1
        stats.total_response_time_ms += response_time_ms
        stats.consecutive_failures = 0  # Reset on success
        self._save_health_data()

        self.logger.debug(
            f"Provider '{provider}' success: {response_time_ms}ms, "
            f"total={stats.success_count}, rate={self._get_success_rate(stats):.2%}"
        )

    def record_failure(self, provider: str) -> None:
        """
        Record a failed API call.

        Args:
            provider: Provider identifier
        """
        stats = self._get_stats(provider)
        stats.fail_count += 1
        stats.consecutive_failures += 1
        stats.last_failure = datetime.now().isoformat()
        self._save_health_data()

        self.logger.debug(
            f"Provider '{provider}' failure: consecutive={stats.consecutive_failures}, "
            f"total_fails={stats.fail_count}"
        )

    def _get_success_rate(self, stats: ProviderStats) -> float:
        """Calculate success rate for a provider."""
        total = stats.success_count + stats.fail_count
        if total == 0:
            return 1.0  # New provider, assume good
        return stats.success_count / total

    def _get_avg_response_time_ms(self, stats: ProviderStats) -> float:
        """Calculate average response time in ms."""
        if stats.success_count == 0:
            return self.MAX_ACCEPTABLE_RESPONSE_TIME_MS / 2  # Default for new providers
        return stats.total_response_time_ms / stats.success_count

    def _calculate_priority_score(self, provider: str) -> float:
        """
        Calculate priority score for a provider.

        Higher score = better provider, should be tried first.

        Factors:
        - Success rate (40% weight)
        - Response time (30% weight)
        - Recent stability (30% weight) - penalizes consecutive failures

        Returns:
            Score between 0.0 and 1.0
        """
        stats = self._get_stats(provider)

        # Success rate component (0-1)
        success_rate = self._get_success_rate(stats)

        # Response time component (0-1, lower time = higher score)
        avg_time = self._get_avg_response_time_ms(stats)
        time_score = max(0.0, 1.0 - (avg_time / self.MAX_ACCEPTABLE_RESPONSE_TIME_MS))

        # Stability component (0-1, penalize consecutive failures)
        # Each failure reduces score by 0.25, max penalty = 1.0
        failure_penalty = min(1.0, stats.consecutive_failures * 0.25)
        stability_score = 1.0 - failure_penalty

        # Weighted sum
        score = (
            success_rate * self.WEIGHT_SUCCESS_RATE +
            time_score * self.WEIGHT_RESPONSE_TIME +
            stability_score * self.WEIGHT_RECENT_STABILITY
        )

        return score

    def should_skip_provider(self, provider: str) -> bool:
        """
        Check if provider should be skipped due to circuit breaker.

        Rules:
        - 3 consecutive failures -> skip 1 minute
        - 5 consecutive failures -> skip 5 minutes
        - 10+ consecutive failures -> skip 30 minutes

        Args:
            provider: Provider identifier

        Returns:
            True if provider should be skipped
        """
        stats = self._get_stats(provider)

        if stats.consecutive_failures < self.CIRCUIT_BREAKER_THRESHOLD:
            return False

        if not stats.last_failure:
            return False

        # Determine skip duration based on failure count
        skip_seconds = 1800  # Default: 30 minutes
        for threshold, duration in sorted(self.CIRCUIT_BREAKER_RECOVERY.items()):
            if stats.consecutive_failures >= threshold:
                skip_seconds = duration

        # Parse last failure time
        try:
            last_failure_time = datetime.fromisoformat(stats.last_failure)
            skip_until = last_failure_time + timedelta(seconds=skip_seconds)

            if datetime.now() < skip_until:
                remaining = (skip_until - datetime.now()).total_seconds()
                self.logger.debug(
                    f"Provider '{provider}' circuit breaker active, "
                    f"{remaining:.0f}s remaining"
                )
                return True

            # Circuit breaker expired, allow retry
            self.logger.debug(f"Provider '{provider}' circuit breaker expired, allowing retry")
            return False

        except (ValueError, TypeError) as e:
            self.logger.error(f"Error parsing last_failure time: {e}")
            return False

    def get_priority_sorted_providers(self, providers: List[str]) -> List[str]:
        """
        Sort providers by priority score, filtering out circuit-broken ones.

        Args:
            providers: List of provider identifiers

        Returns:
            Sorted list with highest priority first
        """
        # Filter out circuit-broken providers
        available = [p for p in providers if not self.should_skip_provider(p)]

        if not available:
            # All providers are circuit-broken, allow all as fallback
            self.logger.warning("All providers circuit-broken, allowing all as fallback")
            available = providers

        # Sort by priority score (descending)
        sorted_providers = sorted(
            available,
            key=lambda p: self._calculate_priority_score(p),
            reverse=True
        )

        self.logger.debug(
            f"Provider priority order: {sorted_providers} "
            f"(scores: {[f'{p}={self._calculate_priority_score(p):.2f}' for p in sorted_providers]})"
        )

        return sorted_providers

    def get_adaptive_timeout(self, provider: str) -> float:
        """
        Get adaptive timeout for a provider based on historical performance.

        Args:
            provider: Provider identifier

        Returns:
            Timeout in seconds
        """
        stats = self._get_stats(provider)

        # Not enough data - use default
        if stats.success_count < 3:
            return self.DEFAULT_TIMEOUT

        avg_time_ms = self._get_avg_response_time_ms(stats)

        # Calculate timeout: avg * multiplier + buffer
        timeout_ms = (avg_time_ms * self.TIMEOUT_MULTIPLIER) + self.TIMEOUT_BUFFER_MS
        timeout_seconds = timeout_ms / 1000

        # Clamp to min/max
        timeout = max(self.MIN_TIMEOUT, min(timeout_seconds, self.MAX_TIMEOUT))

        self.logger.debug(
            f"Provider '{provider}' adaptive timeout: {timeout:.1f}s "
            f"(avg={avg_time_ms:.0f}ms)"
        )

        return timeout

    def reset_provider(self, provider: str) -> None:
        """
        Reset health data for a specific provider.

        Args:
            provider: Provider identifier
        """
        if provider in self._health_data:
            del self._health_data[provider]
            self._save_health_data()
            self.logger.info(f"Reset health data for provider '{provider}'")

    def reset_all(self) -> None:
        """Reset all health data."""
        self._health_data = {}
        self._save_health_data()
        self.logger.info("Reset all provider health data")

    def get_stats_summary(self) -> Dict[str, Dict[str, Any]]:
        """
        Get summary of all provider statistics.

        Returns:
            Dictionary with provider stats and calculated metrics
        """
        summary = {}
        for provider, stats in self._health_data.items():
            summary[provider] = {
                'success_count': stats.success_count,
                'fail_count': stats.fail_count,
                'success_rate': f"{self._get_success_rate(stats):.1%}",
                'avg_response_time_ms': int(self._get_avg_response_time_ms(stats)),
                'consecutive_failures': stats.consecutive_failures,
                'priority_score': f"{self._calculate_priority_score(provider):.2f}",
                'circuit_broken': self.should_skip_provider(provider),
            }
        return summary
