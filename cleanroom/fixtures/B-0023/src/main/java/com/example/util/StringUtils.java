package com.example.util;

// VIOLATES ADR-0023: a wildcard import.
import java.util.*;

/** ADR-0006: a utility class is final, so it stays a namespace rather than becoming a type. */
public final class StringUtils {

    private StringUtils() {
    }

    public static String trimToEmpty(String value) {
        return value == null ? "" : value.trim();
    }
}
