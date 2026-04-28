# Async API (`simple_salesforce.aio`)

The `simple_salesforce.aio` subpackage provides async versions of the core
simple-salesforce classes, built on [httpx](https://www.python-httpx.org/) and
Python's `asyncio`. All network calls are non-blocking and must be awaited.

---

## Contents

- [Creating a Client](#creating-a-client)
- [Authentication Methods](#authentication-methods)
- [SObject Operations](#sobject-operations)
- [Queries](#queries)
- [Misc REST Operations](#misc-rest-operations)
- [Bulk API v1](#bulk-api-v1)
- [Bulk API v2](#bulk-api-v2)
- [Metadata API](#metadata-api)
- [Session and Transport Customization](#session-and-transport-customization)
- [Session Refresh](#session-refresh)
- [JSON Parsing Options](#json-parsing-options)

---

## Creating a Client

Because `__init__` cannot be a coroutine, the async client is constructed via
the `build_async_salesforce_client` coroutine rather than by instantiating
`AsyncSalesforce` directly.

```python
import asyncio
from simple_salesforce.aio import build_async_salesforce_client

async def main():
    sf = await build_async_salesforce_client(
        username='user@example.com',
        password='password',
        security_token='token',
    )

asyncio.run(main())
```

The function accepts the same authentication arguments as the synchronous
`Salesforce` class and returns a fully authenticated `AsyncSalesforce` instance.

---

## Authentication Methods

### Username / Password / Security Token

```python
sf = await build_async_salesforce_client(
    username='user@example.com',
    password='password',
    security_token='token',
)
```

To connect to a sandbox, pass `domain='test'`:

```python
sf = await build_async_salesforce_client(
    username='user@example.com.sandbox',
    password='password',
    security_token='token',
    domain='test',
)
```

### IP Filtering with Organization ID

```python
sf = await build_async_salesforce_client(
    username='user@example.com',
    password='password',
    organizationId='00Dxx0000000000',
)
```

### OAuth 2.0 Connected App (username + consumer credentials)

```python
sf = await build_async_salesforce_client(
    username='user@example.com',
    password='password',
    consumer_key='<consumer key>',
    consumer_secret='<consumer secret>',
    domain='login',
)
```

### OAuth 2.0 JWT Bearer Token

Provide either a path to a PEM private key file or the key string directly:

```python
sf = await build_async_salesforce_client(
    username='user@example.com',
    consumer_key='<consumer key>',
    privatekey_file='/path/to/private.key',
    domain='login',
)

# or inline key material
sf = await build_async_salesforce_client(
    username='user@example.com',
    consumer_key='<consumer key>',
    privatekey='-----BEGIN RSA PRIVATE KEY-----\n...',
    domain='login',
)
```

### OAuth 2.0 Client Credentials

Requires a non-standard domain (not `login` or `test`):

```python
sf = await build_async_salesforce_client(
    consumer_key='<consumer key>',
    consumer_secret='<consumer secret>',
    domain='myorg.my',
)
```

### Direct Session ID

```python
sf = await build_async_salesforce_client(
    session_id='<access token>',
    instance='na1.salesforce.com',
)

# or with a full URL
sf = await build_async_salesforce_client(
    session_id='<access token>',
    instance_url='https://na1.salesforce.com',
)
```

---

## SObject Operations

### Accessing SObjects

`AsyncSalesforce` uses `__getattr__` to return `AsyncSFType` instances on
attribute access, the same pattern as the synchronous client:

```python
contact = sf.Contact
lead    = sf.Lead
account = sf.Account
```

### CRUD

All methods are coroutines and must be awaited.

```python
# Create
result = await sf.Contact.create({
    'FirstName': 'Jane',
    'LastName': 'Doe',
    'Email': 'jane.doe@example.com',
})
record_id = result['id']

# Read by ID
record = await sf.Contact.get(record_id)

# Read by external ID
record = await sf.Contact.get_by_custom_id('External_Id__c', 'ABC-123')

# Update
await sf.Contact.update(record_id, {'Email': 'new@example.com'})

# Upsert (returns HTTP status code by default)
status = await sf.Contact.upsert(
    'External_Id__c/ABC-123',
    {'FirstName': 'Jane', 'LastName': 'Doe'},
)

# Delete (returns HTTP status code by default)
status = await sf.Contact.delete(record_id)
```

Pass `raw_response=True` to `upsert`, `update`, or `delete` to receive the
`httpx.Response` object instead of the status code.

### Metadata and Describe

```python
# SObject metadata
meta = await sf.Contact.metadata()

# Full describe (fields, picklists, relationships, ...)
desc = await sf.Contact.describe()

# Describe a specific layout
layout = await sf.Contact.describe_layout(record_id)

# Describe all available SObjects
all_objects = await sf.describe()
```

### Binary (Base64) Attachments

```python
# Upload a file to Salesforce (e.g. Attachment Body)
result = await sf.Attachment.upload_base64(
    '/path/to/file.pdf',
    base64_field='Body',
)

# Update an existing base64 field
await sf.Attachment.update_base64(record_id, '/path/to/new_file.pdf')

# Download binary content
raw_bytes = await sf.Attachment.get_base64(record_id, base64_field='Body')
```

---

## Queries

### Single-Page Query

`query` returns one page of results. The response dict includes `done`,
`totalSize`, `records`, and optionally `nextRecordsUrl`.

```python
result = await sf.query("SELECT Id, Name FROM Account LIMIT 10")
for record in result['records']:
    print(record['Name'])
```

### Paginated Query

`query_more` retrieves the next page when `done` is `False`:

```python
result = await sf.query("SELECT Id, Name FROM Account")
while not result['done']:
    result = await sf.query_more(result['nextRecordsUrl'], identifier_is_url=True)
```

### All-Records Query (eager)

`query_all` pages through all results automatically and returns a single dict
with the complete record list:

```python
result = await sf.query_all("SELECT Id, Name FROM Contact")
print(f"{result['totalSize']} records retrieved")
```

### All-Records Query (lazy / streaming)

`query_all_iter` is an async generator that yields records one at a time
without loading the full result set into memory:

```python
async for record in sf.query_all_iter("SELECT Id, Name FROM Contact"):
    print(record['Name'])
```

Pass `include_deleted=True` to either `query_all` or `query_all_iter` to
include soft-deleted records.

### SOSL Search

```python
# Full SOSL string
result = await sf.search("FIND {Acme} IN Name Fields RETURNING Account(Id, Name)")

# Wrap a plain string in FIND { } automatically
result = await sf.quick_search("Acme")
```

---

## Misc REST Operations

### Generic REST Call

`restful` lets you call any REST path relative to the instance base URL. It
returns `None` for HTTP 204 (No Content) responses.

```python
result = await sf.restful('sobjects/Account/describe/compactLayouts')

# POST with a body
result = await sf.restful(
    'process/approvals',
    method='POST',
    json={'requests': [{'actionType': 'Submit', 'contextId': record_id}]},
)
```

### OAuth2 Endpoints

```python
result = await sf.oauth2('userinfo')
```

### Tooling API

```python
result = await sf.toolingexecute('sobjects/ApexClass/describe')
```

### Apex REST

```python
result = await sf.apexecute('MyApexEndpoint', method='POST', data={'key': 'value'})
```

### API Limits

```python
limits = await sf.limits()
```

After any API call, `sf.api_usage` contains the parsed `Sforce-Limit-Info`
header as a dict of `Usage` and `PerAppUsage` named tuples.

### Sandbox Check

```python
is_sandbox = await sf.is_sandbox()
```

---

## Bulk API v1

Access bulk operations through the `sf.bulk` property, which returns an
`AsyncSFBulkHandler`. Attribute access on the handler returns an
`AsyncSFBulkType` for a given object.

### DML Operations

Each method is an async generator. Consume it with `async for` or collect into
a list:

```python
records = [
    {'FirstName': 'Jane', 'LastName': 'Doe'},
    {'FirstName': 'John', 'LastName': 'Doe'},
]

# Insert
async for result in await sf.bulk.Contact.insert(records):
    print(result)

# Update
async for result in await sf.bulk.Contact.update(
    [{'Id': '003xx...', 'LastName': 'Smith'}]
):
    print(result)

# Upsert by external ID field
async for result in await sf.bulk.Contact.upsert(
    records,
    external_id_field='External_Id__c',
):
    print(result)

# Soft delete
async for result in await sf.bulk.Contact.delete([{'Id': '003xx...'}]):
    print(result)

# Hard delete
async for result in await sf.bulk.Contact.hard_delete([{'Id': '003xx...'}]):
    print(result)
```

### Bulk Query

```python
# Eager — returns a list of result pages
results = await sf.bulk.Contact.query("SELECT Id, Name FROM Contact")

# Lazy — returns an async iterator
results = await sf.bulk.Contact.query(
    "SELECT Id, Name FROM Contact",
    lazy_operation=True,
)
```

### Batch Size and Concurrency

All DML methods accept `batch_size` (default `10000`) and `use_serial`
(default `False`). Pass `batch_size='auto'` to let the library choose a size
that respects the Bulk API v1 10 MB / 10,000-record limits automatically:

```python
async for result in await sf.bulk.Contact.insert(records, batch_size='auto'):
    print(result)
```

### Bypass Results

When you only need to fire-and-forget a bulk job and do not need per-record
results, pass `bypass_results=True`. The iterator yields
`{'bypass_results': True, 'job_id': '...'}` instead of record-level results:

```python
async for info in await sf.bulk.Contact.insert(records, bypass_results=True):
    print(info['job_id'])
```

### Modular DML Helper

`submit_dml` on `AsyncSFBulkHandler` accepts the object name and operation as
strings, which is useful when the object type and operation are determined at
runtime:

```python
results = await sf.bulk.submit_dml(
    object_name='Contact',
    operation='insert',
    data=records,
)

# Upsert requires external_id_field
results = await sf.bulk.submit_dml(
    object_name='Contact',
    operation='upsert',
    data=records,
    external_id_field='External_Id__c',
)
```

---

## Bulk API v2

Access Bulk 2.0 operations through the `sf.bulk2` property, which returns an
`AsyncSFBulk2Handler`. Attribute access on the handler returns an
`AsyncSFBulk2Type` for a given object.

Bulk 2.0 uses CSV data. Records can be supplied as a list of dicts (converted
to CSV internally), as a CSV string, or as a path to a CSV file.

### Ingest Operations

```python
records = [
    {'FirstName': 'Jane', 'LastName': 'Doe', 'Email': 'jane@example.com'},
]

# Insert from a list of dicts
results = await sf.bulk2.Contact.insert(records=records)

# Insert from a CSV file
results = await sf.bulk2.Contact.insert(csv_file='/path/to/contacts.csv')

# Update
results = await sf.bulk2.Contact.update(
    records=[{'Id': '003xx...', 'LastName': 'Smith'}]
)

# Upsert
results = await sf.bulk2.Contact.upsert(
    records=records,
    external_id_field='External_Id__c',
)

# Soft delete (Id column only)
results = await sf.bulk2.Contact.delete(records=[{'Id': '003xx...'}])

# Hard delete
results = await sf.bulk2.Contact.hard_delete(records=[{'Id': '003xx...'}])
```

Each call returns a list of dicts, one per batch submitted:

```python
[
    {
        'numberRecordsFailed': 0,
        'numberRecordsProcessed': 500,
        'numberRecordsTotal': 500,
        'job_id': '750xx...',
    }
]
```

### Bulk 2.0 Query

`query` returns an async generator of CSV strings, one per result page:

```python
async for csv_page in sf.bulk2.Contact.query(
    "SELECT Id, Name FROM Contact WHERE LastName = 'Doe'"
):
    print(csv_page)
```

Use `query_all` to include soft-deleted records:

```python
async for csv_page in sf.bulk2.Contact.query_all("SELECT Id, Name FROM Contact"):
    print(csv_page)
```

Download query results directly to files by passing a `path`:

```python
async for result in sf.bulk2.Contact.query(
    "SELECT Id, Name FROM Contact",
    path='/tmp/results',
):
    print(result['file'])   # path to the downloaded CSV file
```

### Batch Size

Pass `batch_size` to control the maximum records per ingest chunk. The Bulk
2.0 API enforces a 100 MB file-size ceiling per job; the library splits data
accordingly.

---

## Metadata API

The Metadata API is accessible through the `sf.mdapi` property, which returns
an `AsyncSfdcMetadataApi` instance backed by an async Zeep SOAP client.

### File-Based Deployment

```python
# Deploy a zip archive and get back an async process ID
result = await sf.deploy('/path/to/deploy.zip', sandbox=False)
async_id = result['asyncId']

# Poll for status
status = await sf.checkDeployStatus(async_id)
print(status['state'])            # 'Succeeded', 'Failed', etc.
print(status['state_detail'])
print(status['deployment_detail'])
print(status['unit_test_detail'])
```

The `sf.mdapi` property exposes the full `AsyncSfdcMetadataApi` interface for
lower-level Metadata API operations (retrieve, list, create, update, delete,
rename) via the async Zeep client.

---

## Session and Transport Customization

### Custom HTTP Transport

Pass an `httpx.AsyncHTTPTransport` to control connection pooling, SSL
verification, retries, and other low-level HTTP settings:

```python
import httpx
from simple_salesforce.aio import build_async_salesforce_client

transport = httpx.AsyncHTTPTransport(retries=3)
sf = await build_async_salesforce_client(
    username='user@example.com',
    password='password',
    security_token='token',
    transport=transport,
)
```

### Session Factory

For more control, supply a `session_factory`: a zero-argument callable that
returns an `httpx.AsyncClient`. This factory is called for every request.

```python
from functools import partial
import httpx

factory = partial(
    httpx.AsyncClient,
    timeout=httpx.Timeout(30.0),
    verify='/path/to/ca-bundle.crt',
)

sf = await build_async_salesforce_client(
    username='user@example.com',
    password='password',
    security_token='token',
    session_factory=factory,
)
```

### Proxies

Pass a `proxies` dict mapping URL schemes to proxy URLs:

```python
sf = await build_async_salesforce_client(
    username='user@example.com',
    password='password',
    security_token='token',
    proxies={
        'http://':  'http://proxy.internal:3128',
        'https://': 'http://proxy.internal:3128',
    },
)
```

---

## Session Refresh

When constructed via `build_async_salesforce_client` with username/password or
OAuth credentials, the client stores a `login_refresh` callable. On a
`SalesforceExpiredSession` error, most methods will automatically call
`refresh_session()` once and retry.

```python
# Check whether the client can refresh automatically
if sf.can_refresh:
    await sf.refresh_session()
```

For clients constructed with a direct `session_id`, no credential refresh is
possible. `can_refresh` returns `False` and any expired-session error will
propagate to the caller.

---

## JSON Parsing Options

Two options control how JSON responses are decoded:

**`parse_float`** — a callable passed to `json.loads` for float values. Use
`decimal.Decimal` to avoid floating-point precision loss:

```python
import decimal

sf = await build_async_salesforce_client(
    username='user@example.com',
    password='password',
    security_token='token',
    parse_float=decimal.Decimal,
)
```

**`object_pairs_hook`** — a callable used to construct dicts from JSON
objects. Defaults to `collections.OrderedDict`. Pass `dict` or `None` for
plain dicts:

```python
sf = await build_async_salesforce_client(
    ...,
    object_pairs_hook=dict,
)
```
