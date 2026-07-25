# EVAL-G02-037 Report

Result: `pass` on candidate `9adf0ba62f618b15bb41bbb56cec5fdc6229cc8a`.

Three Kafka-focused tests and the full 386-test repository suite passed. The exact candidate deployed
24/24 Ready SUT Deployments. SEED-G02-0013 then sent one candidate-bound synthetic checkout: cart
and checkout both returned 200, and no second stimulus was sent.

The unchanged N=2 fault observations both reported consumer lag 42 and the exact Kafka fault log.
The unchanged two recovery observations were healthy and ended at lag 0. Original and restored flag
digests matched exactly. The 30-second spacing, 90-second deadline, oracle, thresholds, and failure
semantics were unchanged. Gate L2 executions, model calls, fallback, waivers, and open evidence were
all zero.
