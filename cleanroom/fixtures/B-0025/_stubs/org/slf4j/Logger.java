package org.slf4j;

public interface Logger {
    void info(String message);
    void info(String format, Object argument);
    void error(String message, Throwable cause);
}
