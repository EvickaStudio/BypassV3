# reCAPTCHA `webworker.js` — Deobfuscation Method & Findings

This document explains how the obfuscated `recaptcha__de.js` (a copy of Google's
`webworker.js` payload) is structured, how to deobfuscate it, and where the
fingerprint fields that `bypass.py` sends actually come from. It is
**read-only** — it documents the encoder, it does not improve your score (your
own README already established that synthetic fingerprints *lower* the score).

`recaptcha_deob_online.js` is the same file after being run through an online
deobfuscator. It is ~95% identical to the original: it renamed a handful of
locals and stripped one layer of string-array indirection. It did **not**
recover control flow, did **not** resolve the dispatch tables, did **not**
identify the protobuf encoder. Treat it as re-indented, not deobfuscated.

---

## 1. How the file is structured

Strip the license-comment block (lines 1–64 of `recaptcha__de.js`). The payload
starts at line 65:

```js
var w=function(){return[ function(K,X,z,...){...}, function(...){...}, ... ]}();
var t=function(){return[ ... ]}();
var Q=function(){return[ ... ]}();
var L=function(){return[ ... ]}();
var O=function(){return[ ... ]}();
var y=function(){return[ ... ]}();
var Z=function(){return[ ... ]}();
var J=function(){return[ ... ]}();
var B=function(){return[ ... ]}();
var p=function(){return[ ... ]}();
var x=function(){return[ ... ]}();
```

Each of `w`, `t`, `Q`, `L`, `O`, `y`, `Z`, `J`, `B`, `p`, `x` is an **array of
anonymous functions**. Every "call" in the program is `TABLE[index](K, X, z, ...)`.
The `index` picks the function; the first argument `K` is a **dispatch key**
that selects which branch of that function runs.

### The dispatch-key trick

Every function body is a chain of mutually-exclusive guards:

```js
function(K,X,z,V,M,...){
  if((K & 76)==K){ /* branch A */ return ...; }
  if((K+6 & 14)==2){ /* branch B */ return ...; }
  if((K-1|18)>=(K-2&3)){ /* branch C */ return ...; }
  ...
}
```

The compiler picks `K` values so that exactly one guard matches per call. So
`Q[30](13, n, "MerVUtRoajKEbP7pLiGXkL28", 4, A)` and
`Q[30](12, G, navigator.userAgent, 12, A)` enter `Q[30]` with different `K`
(`13` vs `12`) and therefore run different branches — even though they look
like the same call site.

### Control-flow flattening

Many branches internally flatten loops/switches into a state machine:

```js
for(T=66; T!=47; ){
  if(T==66) T = (cond ? 71 : 96);
  if(T==71) { ...; T=61; }
  if(T==96) T = (x!=z ? 89 : 61);
  if(T==89) { ...; T=61; }
  if(T==61) { ...; T=47; }
}
```

A real deobfuscation has to symbolically execute or trace each `K` to fold
these back into normal `if/else/for`. That is days of work and not needed to
understand the fingerprint pipeline — string-anchored greps get you there.

---

## 2. Anchor strings — the reproducible entry points

Google obfuscates names but **cannot obfuscate API contracts**. These strings
are stable across versions and locate every subsystem. Grep for them on any
future `webworker.js`:

| String | Locates | Line (this version) |
|---|---|---|
| `"rresp"` | reload response parser / token extraction | 1349 |
| `"MerVUtRoajKEbP7pLiGXkL28"` | magic fingerprint-key constant | 209 |
| `https://www.google.com/recaptcha/api2/` | URL builder for reload/anchor | 82 |
| `onChallengeExpired` | challenge-lifecycle controller | 67, 1711 |
| `navigator.userAgentData` | Client Hints (UA-CH) collector | 411, 1537 |
| `getHighEntropyValues` | high-entropy UA-CH fetch | 411 |
| `navigator.deviceMemory` | device-memory probe | 1709 |
| `navigator.mediaDevices` / `enumerateDevices` | media-device probe | 607, 730 |
| `performance.timeOrigin` / `performance.now()` | timing seeds | 209, 1709 |
| `/recaptcha/api2/jserrorlogging` | error-reporting endpoint | 470 |

If you capture a future version, run these greps first — they pin the same
code regions this document describes, even after Google reindexes the dispatch
tables.

---

## 3. The protobuf reload encoder

`bypass.py` builds fields `1,2,6,8,14` (+ `5,7,16,20,22,25,28,29` if a
fingerprint is supplied). In `webworker.js` the encoder is the call pattern:

```js
Q[30](FIELD_INDEX, target_msg, value, WIRE_TYPE, A)
```

`Q[30]` is the field-writer dispatcher. `FIELD_INDEX` is the protobuf field
number (not a table index — the obfuscator left the field numbers literal).
`WIRE_TYPE` is `2` (length-delimited / string) or `0` (varint). `A` is the
shared message-builder object.

Concrete occurrences (this version):

| Field | Wire | Evidence (line) | Contents |
|---|---|---|---|
| 1 | 2 | `Q[30](14,G,v_value,1,A)`-style | script version `v` |
| 2 | 2 | `Q[30](...,...,c,...)` | anchor token `c` |
| 8 | 2 | `Q[30](15,G,V[J_.wq],8,A)` | **action** (the field `bypass.py` embeds) |
| 11 | 2 | `Q[30](11,G,V[QY.wq],11,A)` | extra metadata |
| 14 | 2 | `Q[30](14,G,V[W9.wq],z,A)` | site key `k` |
| 3 | 0 | `Q[4](41,mL,n,void 0,p[13](10,k[0],X),3)` | int field |
| 4 | 2 | `Q[4](43,mL,M,void 0,t[2](34,X),4)` | string field |

The `Q[30]` / `Q[4]` split is just two encoders for two message types (the
reload body vs. a nested sub-message). The wire format is identical to what
`bypass.py`'s `_encode_field` produces — Google's encoder and the Python
one-liner write the same bytes.

**This is the key finding for reproduction**: the protobuf schema is *not*
declared anywhere as a `.proto`. It is built imperatively by calling
`Q[30](fieldnum, ...)`. To discover the schema on a future version, grep for
`Q[30](` (or whatever the new dispatcher name is — find it by locating the
`"rresp"` response handler and reading backwards) and list every
`(field_number, wire_type)` pair.

---

## 4. Where each fingerprint field comes from

Matched against `README.md`'s field table and `extract_fingerprint.py`:

### Field 5 — negative integer (hash/seed)
Source: a hash derived from timing/UA data. Built around `performance.timeOrigin`
and `Date.now()` (line 209) and folded through `Q[30](...,n,"MerVUtRoajKEbP7pLiGXkL28",4,A)`
— the magic string is the hash-function selector. Not reproducible without
running the exact closure that produces it.

### Field 7 — opaque token (`05AD5oO3...`)
**Server-provided**, not client-generated. Google hands it back in a prior
reload response (it is the `rresp`-adjacent field in the JSON array). The
client echoes it on the next reload. This is why reusing a captured field 7
works for ~20 requests and then gets flagged: it is a server-issued session
token, and reuse across sessions is the detection signal.

### Field 16 — large opaque blob (canvas/audio fingerprint)
Built by the canvas-rendering + `AudioContext` probe subsystem. The relevant
DOM hooks are `rc-canvas-canvas` / `getContext` (lines 1587, 1591, 1595). The
blob is the serialized output of a fixed canvas draw + an `OfflineAudioContext`
render. Both are device-bound (GPU/driver/audio-stack differences). Random
bytes are trivially detected — the blob has internal checksums and a
plausible entropy distribution that RNG output does not match.

### Field 20 — base64 JSON: perf timing + host list
Built from `performance.now()` samples and the set of hosts the page loaded
resources from. `extract_fingerprint.py` decodes it to:
```json
[[[5006,44],[64607,1],[35837,1]], null,
 [null,null,null,[4,5.75,0.0011,15],[238,0.0588,0.0007,1],0,0,0],
 ["2captcha.com","static.cloudflareinsights.com","www.google.com","www.gstatic.com"],
 [1,440]]
```
The numbers are `PerformanceEntry` timing buckets. Synthesizing them is what
`generate_fingerprint.py` attempts; the values look plausible but the *joint
distribution* with fields 16/22 is what the model scores on.

### Field 22 — base64 binary: JS environment probes
The most device-specific field. Aggregates:
- `navigator.userAgentData.brands` + `mobile` (line 411, 1537)
- `getHighEntropyValues` for `platform`, `platformVersion`, `architecture`,
  `model`, `uaFullVersion` (the `AU` array, line 859)
- `navigator.deviceMemory` (line 1709)
- `navigator.mediaDevices.enumerateDevices` → `videoinput` count (line 607)
- `isSecureContext` gate (line 607)
- `screen.availHeight` / `availWidth` (line 380)
- `maxTouchPoints` (line 1637, 1642)

The binary is a custom packed format (varint-prefixed records), not protobuf.
Reproducing it requires emitting a byte-exact match for the real encoder's
field order and packing — and any mismatch in one sub-probe invalidates the
whole blob.

### Field 25 — base64 JSON: mouse/touch event array
Encoded mouse/touch trajectory. `[[[eventId,delta],[eventId,delta],...]]`.
The `eventId` values (`5006`, `64607`, `35837`) are `PerformanceEventTiming`
ids. Synthetic trajectories (straight lines, uniform timestamps) are detected;
real ones have micro-jitter and correlation with field 20's timing buckets.

### Fields 28 / 29 — anchor-ms / execute-ms
**Not from `webworker.js` at all** — they come from the anchor URL query string.
`extract_fingerprint.py` reads them straight from the captured body; `bypass.py`
sends them as int fields. No deobfuscation needed.

---

## 5. Response parsing

The reload response is `)]}'`-prefixed JSON. The handler is anchored by
`yL=["rresp", ...]` (line 1349). The XSSI guard `)]}'` is stripped, then the
array is read: `arr[0]=="rresp"`, `arr[1]` is the token, `arr[3]` is the TTL.
This is exactly what `bypass.py:parse_reload_response` does — the Python
reimplementation is faithful.

---

## 6. Reproducing this on a future version

1. **Fetch `webworker.js`** — the script URL is in the anchor page HTML
   (`<script src=".../webworker.js">` or loaded by the recaptcha bootstrap).
2. **Strip the license block** (everything in `/* ... */` before the first
   `var w=function(){...}()`).
3. **Locate the dispatch tables** — `grep -n "function(){return\["` lists
   every `w/t/Q/L/O/y/Z/J/B/p/x` table. The function names (`w`, `Q`, ...) will
   change between versions; the *pattern* (`var NAME=function(){return[...]};`)
   does not.
4. **Anchor on the stable strings** (section 2). These never change because
   they are public API contracts or DOM class names Google's own CSS depends on.
5. **Find the protobuf encoder** by grepping for `"rresp"`, reading the
   handler, and following the call graph backwards to the `Q[30](fieldnum,...)`
   pattern. List every `(fieldnum, wire)` pair — that is the reload schema.
6. **Find the fingerprint probes** by grepping for `navigator.`,
   `performance.`, `screen.`, `mediaDevices`, `getHighEntropyValues`. Each
   access site feeds field 16 / 22 / 5.
7. **Do not attempt full control-flow recovery.** It is not worth it. The
   string anchors + the `Q[30](fieldnum,...)` pattern give you the schema; the
   `navigator.*` access sites give you the probe list. That is the whole
   picture.

---

## 7. Why this does not improve your score

Re-stated from `README.md` lines 29 and 146:

- Fields 7, 16, 22 are **opaque device-bound blobs**. They cannot be
  synthesized meaningfully.
- Field 7 is **server-issued** and reuse-flagged after ~20 requests.
- Synthetic motion data (fields 20, 25) was tested and **lowered** the score.

The encoder you see in `webworker.js` is a **packer**, not a **generator of
plausible lies**. It packages real device output. Reading it tells you the
*shape* of the data; it does not give you data that passes the model.

The levers that actually move the score are the ones in `README.md`:
**IP reputation** (residential vs datacenter) and **fingerprint freshness**
(capture-then-rotate before the ~20-request reuse flag). `bypass.py` is being
updated separately for the freshness lever.
