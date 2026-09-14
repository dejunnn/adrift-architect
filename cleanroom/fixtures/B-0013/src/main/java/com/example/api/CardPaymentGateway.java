package com.example.api;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/** The implementation. Named for what it is, so ADR-0010 is satisfied by the interface above. */
public final class CardPaymentGateway implements PaymentGateway {

    // VIOLATES ADR-0013: java.util.logging alongside SLF4J.
    private static final java.util.logging.Logger JUL =
        java.util.logging.Logger.getLogger("card");
    private static final Logger LOG = LoggerFactory.getLogger(CardPaymentGateway.class);

    @Override
    public void charge(String orderId, long amountInCents) {
        LOG.info("charging order");
    }
}
