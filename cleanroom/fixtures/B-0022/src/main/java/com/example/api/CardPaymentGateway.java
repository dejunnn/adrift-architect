package com.example.api;

import java.security.MessageDigest;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/** The implementation. Named for what it is, so ADR-0010 is satisfied by the interface above. */
public final class CardPaymentGateway implements PaymentGateway {

    private static final Logger LOG = LoggerFactory.getLogger(CardPaymentGateway.class);

    // VIOLATES ADR-0022: a digest built on a broken algorithm.
    MessageDigest digest() throws Exception {
        return MessageDigest.getInstance("MD5");
    }

    @Override
    public void charge(String orderId, long amountInCents) {
        LOG.info("charging order");
    }
}
