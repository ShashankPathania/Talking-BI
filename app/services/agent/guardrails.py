import re
from typing import Tuple, Optional

class SQLValidator:
    """Strict safety validator for AI-generated SQL queries."""
    
    FORBIDDEN_KEYWORDS = {
        "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE", 
        "CREATE", "GRANT", "REVOKE", "EXEC", "EXECUTE", "REPLACE"
    }

    @classmethod
    def validate_and_format(cls, sql: str, max_rows: int = 1000) -> Tuple[bool, str, Optional[str]]:
        """
        Validates that the query is read-only and formats it with safety limits.
        Returns: (is_valid, formatted_sql, error_message)
        """
        clean_sql = sql.strip().strip(";")
        upper_sql = clean_sql.upper()

        # 1. Broad Keyword Check
        # We look for forbidden keywords as standalone words to avoid false positives (e.g. 'Created_At' column)
        for keyword in cls.FORBIDDEN_KEYWORDS:
            if re.search(rf"\b{keyword}\b", upper_sql):
                return False, sql, f"Safety Violation: Forbidden keyword '{keyword}' detected."

        # 2. Strict Read-Only Start Check
        # Query must start with SELECT or WITH
        if not (upper_sql.startswith("SELECT") or upper_sql.startswith("WITH")):
            return False, sql, "Safety Violation: Query must start with SELECT or WITH."

        # 3. Row Limit Guardrail
        if "LIMIT" not in upper_sql:
            clean_sql = f"{clean_sql} LIMIT {max_rows}"
        else:
            # If LIMIT exists, ensure it doesn't exceed our hard cap
            # Regex to find the limit number
            match = re.search(r"LIMIT\s+(\d+)", upper_sql)
            if match:
                requested_limit = int(match.group(1))
                if requested_limit > max_rows:
                    clean_sql = re.sub(r"LIMIT\s+\d+", f"LIMIT {max_rows}", clean_sql, flags=re.IGNORECASE)

        return True, clean_sql, None
