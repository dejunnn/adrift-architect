package com.example.api;

/** ADR-0010: an interface named for the capability, not with an Impl suffix. */
// VIOLATES ADR-0010: an interface carrying an Impl suffix.
public interface PaymentGatewayImpl {

    void charge(String orderId, long amountInCents);
}
