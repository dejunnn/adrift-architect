package com.example.api;

/** ADR-0010: an interface named for the capability, not with an Impl suffix. */
public interface PaymentGateway {

    void charge(String orderId, long amountInCents);
}
