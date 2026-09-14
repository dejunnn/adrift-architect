package org.slf4j;

public final class LoggerFactory {

    private LoggerFactory() {
    }

    public static Logger getLogger(Class<?> type) {
        return new Logger() {
            public void info(String message) { }
            public void info(String format, Object argument) { }
            public void error(String message, Throwable cause) { }
        };
    }
}
