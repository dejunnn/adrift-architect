package com.example.util;

/** ADR-0006: a utility class is final, so it stays a namespace rather than becoming a type. */
// VIOLATES ADR-0006: a Utils class that is not final.
public class StringUtils {

    private StringUtils() {
    }

    public static String trimToEmpty(String value) {
        return value == null ? "" : value.trim();
    }
}
