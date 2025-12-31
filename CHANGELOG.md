<!--
SPDX-FileCopyrightText: 2025 Ilya Egorov <0x42005e1f@gmail.com>
SPDX-License-Identifier: CC-BY-4.0
-->

Changelog
=========

All notable changes to this project will be documented in this file.

The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Commit messages are consistent with
[Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/).

[0.11.0] - 2025-12-31
---------------------

### Added

- `culsans.__version__` and `culsans.__version_tuple__` as a way to retrieve
  the package version at runtime.
- `culsans.Grouper` (initial implementation) as a higher-level synchronization
  primitive with phase-fair priority policy by default. See
  [x42005e1f/aiologic#19](https://github.com/x42005e1f/aiologic/issues/19) for
  details.
- `culsans.RWLock` (initial implementation) as a readers-writer lock that is
  both phase-fair and reentrant. It is currently defined as a subclass of
  `culsans.Grouper`, but this may change in the future.
- `culsans.BaseQueueProxy` as a common superclass for `culsans.SyncQueueProxy`
  and `culsans.AsyncQueueProxy`. Added to reduce code duplication, but can also
  be used separately for other purposes (such as checking that an object is an
  instance of either proxy type).
- `culsans.GreenQueue`, `culsans.GreenQueueProxy`, and methods prefixed with
  `green_`, which make the interfaces `aiologic`-like. They are equivalent to
  their "sync" alternatives and are preferred for new uses.
- `blocking` parameter wherever there is `block` parameter, as its alias. This
  change complements the previous one. Note that none of these parameters have
  been added to async def methods, as this would complicate the implementation,
  so there is still no full compatibility with `aiologic` queues (the
  parameters will be added in the future along with async timeouts).
- `sizer` parameter, corresponding `isize()` public methods, and `_isize`
  protected attribute/method (for overriding). Allows to specify the size for
  each queue item, which affects the put methods. Solves
  [#9](https://github.com/x42005e1f/culsans/issues/9).
- `clearable()` methods and related `culsans.Queue._clearable()` protected
  method (for overriding) analogous to those for peek methods, making
  implementation of the `clear()` method optional. Along with this, the
  `clear()` method is now also used in the implementation of the `shutdown()`
  method, when available.
- `size` property, which returns the cumulative size of items in the queue.
- `green_proxy`/`async_proxy` properties as a more generic alternative to
  `sync_q`/`async_q`.
- The proxies can now be weakly referenced. Previously, this was disallowed due
  to their limited lifetime (since the corresponding properties return new
  objects on each access). This is now allowed for cases where a proxy is used
  as a backport to older versions of Python.
- A negative queue length is now a valid value and is handled correctly
  (extends subclassing capabilities).
- A negative value of the `unfinished_tasks` property is now treated as
  infinity (extends subclassing capabilities).

### Changed

- The queues now override `__len__()` and `__bool__()`, allowing `len(queue)`
  and `bool(queue)` to be used in the same sense as for collections. And while
  this change is not conceptually incompatible, in fact it breaks the
  not-so-good pattern `if self.queue:  # self.queue is not None`.
- The `maxsize` property is now defined as the maximum cumulative size of queue
  items rather than the maximum queue length. This allows arbitrary queue item
  sizes to be supported, but may require existing code to be modified to work
  correctly when passing a custom sizer (as this affects both the put methods
  and the `full()` methods).
- The underlying lock is now reentrant. This differs from the standard queue
  approach, but makes it much easier to create subclasses and also makes
  `culsans.Queue` somewhat compatible with `sqlalchemy.util.queue.Queue`.
  However, the main reason is not this, but to make the following change
  efficiently implemented.
- The queues now rely on new `aiologic` safety guarantees when using the
  condition variables. Previously, as with `threading.Condition`, a
  `KeyboardInterrupt` raised during synchronization on the underlying lock
  after notification led to the lock being over-released and, as a result, to a
  `RuntimeError`. Now, `aiologic.Condition` is used as a context manager,
  thereby including additional checks on the `aiologic` side to ensure that the
  current thread owns the lock when releasing it.
- The `unfinished_tasks` property's value now changes according to the queue
  length change (the value returned by the `_qsize()` method). This allows to
  create flattened queues without introducing related additional methods and
  also corrects the behavior for subclasses that may not change the queue
  length as a result of insertion.
- The `timeout` parameter's value is now checked and converted at the beginning
  of the method call, regardless of the `block` parameter's value. This should
  prevent cases where an incorrect value is passed.
- The peekability check is now ensured before each call (after each context
  switch), allowing the peek methods to be enabled/disabled dynamically.
- The package now relies on `aiologic.meta.export()` for exports instead of
  using its own implementation (similar to `aiologic==0.15.0`), which provides
  safer behavior. In particular, queue methods now also update their metadata,
  allowing them to be safely referenced during pickling.
- The protocols are now inherited from `typing_extensions.Protocol` on Python
  below 3.13, which backports all related fixes and improvements to older
  versions of Python.
- The shutdown exceptions are now defined again via backports (on Python below
  3.13), but in a type-friendly manner.

### Fixed

- The sync methods called the checkpoint function regardless of the `block`
  parameter's value. Now they do not make the call in the non-blocking case.
- Notifications could be insufficient or excessive when the queue length
  changed differently than in the standard behavior. Now such situations are
  detected and a different notification mechanism is activated when they are
  detected.

[0.10.0] - 2025-11-04
---------------------

### Added

- `culsans.Queue.waiting` as the third `aiologic`-like property. Useful when
  you need to reliably obtain the total number of waiting ones.
- Timeout handling has been improved in line with the latest changes in
  `aiologic` (support for very large numbers, additional checking for `NaN`,
  use of the clock functions from `aiologic.lowlevel`). This is particularly
  relevant for `aiologic>=0.15.0`, which implements safe timeouts, but has
  almost no impact on older versions.
- The properties of `culsans.Queue` now return proxies instead of protocols for
  type checkers. This allows, for example, accessing the wrapped queue via the
  proxy attribute without type errors.
- The proxies are now represented in a readable format, which should make
  debugging a little easier.

### Changed

- The priority queues now use stricter bounds for the type variable: collection
  elements must be rich comparable (implement `__lt__()` or `__gt__()` method).
  This corresponds to recent changes in `typeshed` for the standard queues (see
  [python/typeshed#14418](https://github.com/python/typeshed/issues/14418)) and
  makes them safer.

### Fixed

- For the underlying lock, `aiologic.lowlevel._thread` was used, which has been
  declared deprecated in the latest version of `aiologic`.
- With green checkpoints enabled, the end time was recalculated for the timeout
  after rescheduling, which could lead to doubling the actual wait time
  (`0.9.0` regression).

[0.9.0] - 2025-07-16
--------------------

### Changed

- Checkpoint functions are now always called before queue operations are
  performed (previously they were called after). This ensures that all queue
  methods behave as expected on cancellations, but it may increase the number
  of explicit context switches.
- The build system has been changed from `setuptools` to `uv` + `hatch`. It
  keeps the same `pyproject.toml` format, but has better performance, better
  logging, and builds cleaner source distributions (without `setup.cfg`).
- The version identifier is now generated dynamically and includes the latest
  commit information for development versions, which simplifies bug reporting.
  It is also passed to archives generated by GitHub (via `.git_archival.txt`)
  and source distributions (via `PKG-INFO`).

### Fixed

- For asynchronous checkpoints, `aiologic.lowlevel.checkpoint()` was used,
  which has been declared deprecated in the latest version of `aiologic`.
- With checkpoints enabled (`trio` case by default), the get methods could lose
  items on cancellations, and for the put methods, it was impossible to
  determine whether the put was successful or not on the same cancellations
  (`0.2.1` regression).

[0.8.0] - 2025-01-19
--------------------

### Added

- Python 3.8 support. This makes the list of supported versions consistent with
  that of `aiologic`. Previously, the lowest supported version was 3.9.
- `culsans.MixedQueue` as a queue protocol that provides both types of blocking
  methods via prefixes. Can be used to generalize `culsans.Queue` and its
  derivatives by type checkers, as it does not include `janus.Queue`-specific
  and other foreign methods and properties/attributes.

### Changed

- Interfaces and type hints have been improved:
  + Now `aiologic>=0.13.0` is used (previously `>=0.12.0` was used), which
    provides type annotations. This removes mypy-specific type ignores.
  + All fields are annotated. A side effect is that the queue subclasses now
    define their own slot for storing data.
- The source code tree has been significantly changed for better IDEs support.
  The same applies to exports, which are now checker-friendly.

[0.7.1] - 2024-12-23
--------------------

### Fixed

- For `culsans.QueueShutDown` on Python below 3.13, backported exceptions were
  defined, but they caused name conflicts for type checkers. Now, all queue
  shutdown exceptions reference the same class (on Python below 3.13).

[0.7.0] - 2024-12-23
--------------------

### Added

- `culsans.QueueEmpty`, `culsans.QueueFull`, and `culsans.QueueShutDown` as
  exceptions compatible with any interface (they inherit both types). They are
  now also raised instead of specialized exceptions, allowing any type to be
  used in try-catch.
- The remaining non-blocking methods and both types of blocking methods to
  `culsans.Queue` via prefixes (`sync_` and `async_`). The main reason for this
  is to move the entire implementation from the proxy classes to the queue
  classes. However, they can also be used as a simpler, shorter style of
  working with queues (similar to `aiologic`, but with `sync_` instead of
  `green_`).
- `culsans.Queue.putting` and `culsans.Queue.getting` as `aiologic`-like
  properties. They can be used to obtain the number of waiting ones for a given
  operation type. But note, `culsans.Queue.getting` also includes the number of
  peekers.
- `culsans.Queue` now inherits from `culsans.BaseQueue` instead of `Generic`.
  This improves type safety and allows introspection at runtime.
- Direct access (without the `_` prefix) to the synchronization primitives
  used, to better mimic the `queue` module.

[0.6.0] - 2024-12-14
--------------------

### Changed

- The behavior of Janus-specific methods now corresponds to `janus>=2.0.0`
  (instead of `1.2.0`). The only change is that after calling
  `culsans.Queue.close()`, `*QueueShutDown` is now raised instead of
  `RuntimeError`.

[0.5.0] - 2024-12-14
--------------------

### Added

- `culsans.Queue.aclose()` method, which replicates the behavior of the
  same-named Janus method. This makes the interface compliant with the Janus
  API version 1.2.0 (instead of 1.1.0).

[0.4.0] - 2024-11-17
--------------------

### Added

- `peekable()` methods and related `culsans.Queue._peekable()` protected method
  (for overriding). They simplify non-peekable subclass creation by providing a
  unified contract for how to deal with it from the user's side.
- `culsans.UnsupportedOperation` exception, which is raised when attempting to
  call any of the peek methods for a non-peekable queue.

[0.3.0] - 2024-11-08
--------------------

### Added

- `culsans.Queue.close()` and `culsans.Queue.wait_closed()` methods,
  `culsans.Queue.closed` property to implement compatibility with
  `janus>=1.1.0`. For the most part, they behave similarly to the originals
  (including the exception raised after closing), but semantically they are
  closer to the queue shutdown methods from Python 3.13. This differs from the
  `janus` behavior, but solves
  [aio-libs/janus#237](https://github.com/aio-libs/janus/issues/237).
- `peek()` and `peek_nowait()` methods, related `culsans.Queue._peek()`
  protected method (for overriding), as a way to retrieve an item from a queue
  without removing it. In a sense, they implement partial compatibility with
  the `gevent` queues, but peek/front is also a well-known third type of queue
  operation.
- `clear()` method and related `culsans.Queue._clear()` protected method (for
  overriding). Atomically clears the queue, ensuring that other threads do not
  affect the clearing process, and updates the `unfinished_tasks` property at
  the same time. Solves
  [aio-libs/janus#645](https://github.com/aio-libs/janus/issues/645).

[0.2.1] - 2024-11-04
--------------------

### Fixed

- Mixed use of both types of methods could lead to deadlocks (due to the use of
  a shared wait queue for the underlying lock). This could be considered
  expected behavior if it did not also affect non-blocking methods (due to the
  blocking use of the condition variables).

[0.2.0] - 2024-11-04
--------------------

### Added

- `culsans.Queue.maxsize` can now be changed dynamically at runtime (growing &
  shrinking). This allows for more complex logic to be implemented, whereby the
  maximum queue size is adjusted according to certain external conditions.
  Related:
  [python/cpython#54319](https://github.com/python/cpython/issues/54319).

### Changed

- The protocols, and therefore the proxies, no longer include the implicit
  `__dict__`, thereby preventing unknown attributes from being set. This makes
  them safer.

[0.1.0] - 2024-11-02
--------------------

### Added

- Janus-like mixed queues and all related API (excluding some Janus-specific
  methods that seem redundant on Python 3.13, in favor of new methods such as
  `shutdown()`). They use the same patterns as the `queue` module, but rely on
  the condition variables from `aiologic`. This makes them 4-8 times faster
  than `janus.Queue` in multi-threaded tests, simplifies usage, and expands the
  number of supported use cases (multiple event loops, `trio` support, etc.).

[0.11.0]: https://github.com/x42005e1f/culsans/compare/0.10.0...0.11.0
[0.10.0]: https://github.com/x42005e1f/culsans/compare/0.9.0...0.10.0
[0.9.0]: https://github.com/x42005e1f/culsans/compare/0.8.0...0.9.0
[0.8.0]: https://github.com/x42005e1f/culsans/compare/0.7.1...0.8.0
[0.7.1]: https://github.com/x42005e1f/culsans/compare/0.7.0...0.7.1
[0.7.0]: https://github.com/x42005e1f/culsans/compare/0.6.0...0.7.0
[0.6.0]: https://github.com/x42005e1f/culsans/compare/0.5.0...0.6.0
[0.5.0]: https://github.com/x42005e1f/culsans/compare/0.4.0...0.5.0
[0.4.0]: https://github.com/x42005e1f/culsans/compare/0.3.0...0.4.0
[0.3.0]: https://github.com/x42005e1f/culsans/compare/0.2.1...0.3.0
[0.2.1]: https://github.com/x42005e1f/culsans/compare/0.2.0...0.2.1
[0.2.0]: https://github.com/x42005e1f/culsans/compare/0.1.0...0.2.0
[0.1.0]: https://github.com/x42005e1f/culsans/releases/tag/0.1.0
