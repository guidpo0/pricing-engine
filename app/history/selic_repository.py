"""
Repository for SELIC daily factors (BCB SGS series 12).

Stores individual daily SELIC factors so the LFT VNA can be
computed for any historical reference date.
"""
from __future__ import annotations

import logging
from datetime import date as date_type
from typing import Optional

from app.history.history_repository import _get_connection, _return_connection

logger = logging.getLogger(__name__)


def upsert_selic_factors_batch(data: list[dict], anchor_date: date_type) -> int:
    """
    Insert or update daily SELIC factors from BCB raw response into the DB.

    Only entries with factor_date > anchor_date are stored, using
    INSERT ON CONFLICT DO NOTHING so previously saved dates are preserved.

    Args:
        data: Raw JSON list from BCB SGS series 12, each entry has
              {"data": "DD/MM/YYYY", "valor": "0,XXXX"}.
        anchor_date: Skip entries on or before this date.

    Returns:
        Number of rows inserted.
    """
    conn = _get_connection()
    inserted = 0
    try:
        with conn.cursor() as cur:
            for entry in data:
                day, month, year = entry["data"].split("/")
                factor_date = date_type(int(year), int(month), int(day))
                if factor_date <= anchor_date:
                    continue
                daily_factor = float(entry["valor"].replace(",", ".")) / 100.0
                cur.execute(
                    """INSERT INTO selic_daily_factors (factor_date, daily_factor)
                       VALUES (%s, %s)
                       ON CONFLICT (factor_date) DO NOTHING""",
                    (factor_date, daily_factor),
                )
                if cur.rowcount > 0:
                    inserted += 1
            conn.commit()
        if inserted:
            logger.info("Inserted %d new SELIC daily factors into DB", inserted)
    except Exception as exc:
        logger.error("Failed to upsert SELIC factors: %s", exc)
        conn.rollback()
    finally:
        _return_connection(conn)
    return inserted


def get_selic_factors_up_to(ref_date: date_type) -> list[dict]:
    """
    Retrieve all stored SELIC daily factors up to (and including) ref_date,
    ordered chronologically.

    Args:
        ref_date: Maximum factor_date to include.

    Returns:
        List of {"factor_date": date, "daily_factor": float} dicts.
    """
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT factor_date, daily_factor
                   FROM selic_daily_factors
                   WHERE factor_date <= %s
                   ORDER BY factor_date ASC""",
                (ref_date,),
            )
            rows = cur.fetchall()
        return [
            {"factor_date": row[0], "daily_factor": float(row[1])}
            for row in rows
        ]
    except Exception as exc:
        logger.error("Failed to read SELIC factors: %s", exc)
        return []
    finally:
        _return_connection(conn)


def get_max_factor_date() -> Optional[date_type]:
    """
    Get the latest (maximum) factor_date stored in the DB.

    Returns:
        The latest date, or None if the table is empty.
    """
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT MAX(factor_date) FROM selic_daily_factors"""
            )
            result = cur.fetchone()
            return result[0] if result and result[0] else None
    except Exception as exc:
        logger.error("Failed to get max SELIC factor date: %s", exc)
        return None
    finally:
        _return_connection(conn)
