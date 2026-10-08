import hashlib
import json
import logging
import re
import time
import unicodedata
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

# In-memory fallback if Redis is offline
_IN_MEMORY_CACHE: dict[str, dict[str, Any]] = {}
_IN_MEMORY_QUESTIONS: dict[str, list[dict[str, Any]]] = {}


def remove_accents(text: str) -> str:
    """Removes Vietnamese tone marks and accents for robust fuzzy matching."""
    text = text.replace("đ", "d").replace("Đ", "d")
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalize_text(text: str) -> str:
    """Normalize user question text for cache matching."""
    text = text.lower().strip()
    text = remove_accents(text)
    # Remove punctuation
    text = re.sub(r"[?!.,;:\"'()[\]{}<>]+", " ", text)
    # Collapse multiple spaces
    text = re.sub(r"\s+", " ", text).strip()
    return text


def compute_similarity(q1: str, q2: str) -> float:
    """Computes hybrid Jaccard & Overlap similarity for search questions."""
    tokens1 = set(q1.split())
    tokens2 = set(q2.split())
    if not tokens1 or not tokens2:
        return 0.0
    intersection = tokens1.intersection(tokens2)
    union = tokens1.union(tokens2)
    jaccard = len(intersection) / len(union)
    overlap = len(intersection) / min(len(tokens1), len(tokens2))

    return 0.5 * jaccard + 0.5 * overlap


class CacheService:
    """Two-tier Semantic & Exact Cache Service backed by Redis with in-memory fallback."""

    def __init__(self) -> None:
        self.redis_client = None
        try:
            import redis

            self.redis_client = redis.Redis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_timeout=1.5,
                socket_connect_timeout=1.5,
            )
            # Ping test
            self.redis_client.ping()
            logger.info("Connected to Redis cache at %s", settings.redis_url)
        except Exception as e:
            logger.warning("Redis unavailable (%s). Falling back to in-memory cache.", e)
            self.redis_client = None

    def _get_exact_key(self, dataset_id: int, rls_key: str, norm_q: str) -> str:
        q_hash = hashlib.sha256(norm_q.encode("utf-8")).hexdigest()[:16]
        safe_rls = hashlib.md5((rls_key or "none").encode("utf-8")).hexdigest()[:8]
        return f"ai_bi:qa:{dataset_id}:{safe_rls}:{q_hash}"

    def _get_index_key(self, dataset_id: int, rls_key: str) -> str:
        safe_rls = hashlib.md5((rls_key or "none").encode("utf-8")).hexdigest()[:8]
        return f"ai_bi:idx:{dataset_id}:{safe_rls}"

    def get(
        self,
        question: str,
        dataset_id: int,
        rls_filter: str | None = None,
        similarity_threshold: float = 0.85,
    ) -> dict[str, Any] | None:
        """Lookup question in cache via Exact match, then Semantic similarity."""
        start_time = time.time()
        norm_q = normalize_text(question)
        rls_key = (rls_filter or "").strip()
        exact_key = self._get_exact_key(dataset_id, rls_key, norm_q)

        # 1. Exact Match via Redis or in-memory
        if self.redis_client:
            try:
                cached_str = self.redis_client.get(exact_key)
                if cached_str:
                    data = json.loads(cached_str)
                    latency_ms = round((time.time() - start_time) * 1000, 1)
                    data["cache_hit"] = True
                    data["cache_type"] = "exact"
                    data["latency_ms"] = latency_ms
                    return data
            except Exception as e:
                logger.warning("Redis get error: %s", e)
        else:
            if exact_key in _IN_MEMORY_CACHE:
                data = dict(_IN_MEMORY_CACHE[exact_key])
                latency_ms = round((time.time() - start_time) * 1000, 1)
                data["cache_hit"] = True
                data["cache_type"] = "exact"
                data["latency_ms"] = latency_ms
                return data

        # 2. Semantic Similarity Match
        # Scan candidate questions for same dataset & rls
        idx_key = self._get_index_key(dataset_id, rls_key)
        candidates: list[dict[str, Any]] = []

        if self.redis_client:
            try:
                raw_items = self.redis_client.lrange(idx_key, 0, 100)
                candidates = [json.loads(item) for item in raw_items]
            except Exception as e:
                logger.warning("Redis index scan error: %s", e)
        else:
            candidates = _IN_MEMORY_QUESTIONS.get(idx_key, [])

        best_match = None
        best_score = 0.0

        for cand in candidates:
            score = compute_similarity(norm_q, cand.get("norm_q", ""))
            if score > best_score:
                best_score = score
                best_match = cand

        if best_match and best_score >= similarity_threshold:
            # Found semantic match! Retrieve corresponding full cached item
            target_key = best_match.get("key")
            if target_key:
                if self.redis_client:
                    try:
                        raw_data = self.redis_client.get(target_key)
                        if raw_data:
                            data = json.loads(raw_data)
                            latency_ms = round((time.time() - start_time) * 1000, 1)
                            data["cache_hit"] = True
                            data["cache_type"] = "semantic"
                            data["similarity"] = round(best_score, 2)
                            data["latency_ms"] = latency_ms
                            return data
                    except Exception as e:
                        logger.warning("Redis target get error: %s", e)
                elif target_key in _IN_MEMORY_CACHE:
                    data = dict(_IN_MEMORY_CACHE[target_key])
                    latency_ms = round((time.time() - start_time) * 1000, 1)
                    data["cache_hit"] = True
                    data["cache_type"] = "semantic"
                    data["similarity"] = round(best_score, 2)
                    data["latency_ms"] = latency_ms
                    return data

        return None

    def set(
        self,
        question: str,
        dataset_id: int,
        rls_filter: str | None,
        response_payload: dict[str, Any],
        ttl_seconds: int = 7200,
    ) -> None:
        """Saves a query answer in both the exact cache and semantic search index."""
        norm_q = normalize_text(question)
        rls_key = (rls_filter or "").strip()
        exact_key = self._get_exact_key(dataset_id, rls_key, norm_q)
        idx_key = self._get_index_key(dataset_id, rls_key)

        cache_obj = {
            "question": question,
            "normalized_question": norm_q,
            "dataset_id": dataset_id,
            "response": response_payload,
            "cached_at": int(time.time()),
        }

        index_item = {
            "key": exact_key,
            "norm_q": norm_q,
            "original_q": question,
        }

        if self.redis_client:
            try:
                self.redis_client.set(exact_key, json.dumps(cache_obj), ex=ttl_seconds)
                self.redis_client.lpush(idx_key, json.dumps(index_item))
                self.redis_client.ltrim(idx_key, 0, 100)
                self.redis_client.expire(idx_key, ttl_seconds)
            except Exception as e:
                logger.warning("Redis set error: %s", e)
        else:
            _IN_MEMORY_CACHE[exact_key] = cache_obj
            if idx_key not in _IN_MEMORY_QUESTIONS:
                _IN_MEMORY_QUESTIONS[idx_key] = []
            _IN_MEMORY_QUESTIONS[idx_key].insert(0, index_item)
            _IN_MEMORY_QUESTIONS[idx_key] = _IN_MEMORY_QUESTIONS[idx_key][:100]

    def clear(self) -> None:
        """Clears all query caches."""
        if self.redis_client:
            try:
                keys = self.redis_client.keys("ai_bi:*")
                if keys:
                    self.redis_client.delete(*keys)
            except Exception as e:
                logger.warning("Redis clear error: %s", e)
        _IN_MEMORY_CACHE.clear()
        _IN_MEMORY_QUESTIONS.clear()


cache_service = CacheService()
