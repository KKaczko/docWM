# Summary Report

## Packages

| Package | Services | Inferred |
| --- | ---: | --- |
| `SampleOrder` | 3 | False |

## Document Types

| Document | Package |
| --- | --- |
| `com.example.docs:Order` | `SampleOrder` |

## Validation Issues

| Severity | Code | Message | Service |
| --- | --- | --- | --- |
| warning | `DYNAMIC_INVOKE_TARGET_UNKNOWN` | Dynamic invocation via 'pub.flow:invoke' at step 0.0.2; target cannot be resolved statically. | `com.example.order:submitOrder` |
| warning | `JAVA_SOURCE_NOT_FOUND` | Java service implementation source could not be found by service name. | `com.example.billing:createInvoice` |
