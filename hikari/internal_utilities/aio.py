#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright © Nekokatt 2019-2020
#
# This file is part of Hikari.
#
# Hikari is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Hikari is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with Hikari. If not, see <https://www.gnu.org/licenses/>.
"""
Asyncio extensions and utilities.
"""
from __future__ import annotations

import asyncio
import contextlib
import functools
import typing
import weakref

import async_timeout

from hikari.internal_utilities import assertions
from hikari.internal_utilities import type_hints

ReturnT = typing.TypeVar("ReturnT", covariant=True)
CoroutineFunctionT = typing.Callable[..., typing.Coroutine[typing.Any, typing.Any, ReturnT]]


def optional_await(
    description: str = None, shield: bool = False
) -> typing.Callable[
    [typing.Callable[..., typing.Coroutine[typing.Any, typing.Any, ReturnT]]],
    typing.Callable[..., typing.Awaitable[ReturnT]],
]:
    """
    Optional await decorator factory for async functions so that they can be called without await and
    scheduled on the event loop lazily.

    Args:
        description:
            the optional name to give the dispatched task.
        shield:
            defaults to False. If `True`, the coroutine will be wrapped in a :func:`asyncio.shield`
            to prevent it being cancelled.

    Returns:
        A decorator for a coroutine function.
    """

    def decorator(
        coro_fn: typing.Callable[..., typing.Coroutine[typing.Any, typing.Any, ReturnT]]
    ) -> typing.Callable[..., typing.Awaitable[ReturnT]]:
        @functools.wraps(coro_fn)
        def wrapper(*args, **kwargs) -> typing.Awaitable[ReturnT]:
            coro = asyncio.shield(coro_fn(*args, **kwargs)) if shield else coro_fn(*args, **kwargs)
            return asyncio.create_task(coro, name=description)

        return wrapper

    return decorator


class PartialCoroutineProtocolT(typing.Protocol[ReturnT]):
    """Represents the type of a :class:`functools.partial` wrapping an :mod:`asyncio` coroutine."""

    def __call__(self, *args, **kwargs) -> typing.Coroutine[None, None, ReturnT]:
        ...

    def __await__(self):
        ...


class EventDelegate:
    """Handles storing and dispatching to event listeners and one-time event
    waiters.

    Event listeners once registered will be stored until they are manually
    removed. Each time an event is dispatched with a matching name, they will
    be invoked on the event loop.

    One-time event waiters are futures that will be completed when a matching
    event is fired. Once they are matched, they are removed from the listener
    list. Each listener has a corresponding predicate that is invoked prior
    to completing the waiter, with any event parameters being passed to the
    predicate. If the predicate returns False, the waiter is not completed. This
    allows filtering of certain events and conditions in a procedural way.
    """

    def __init__(self) -> None:
        self._listeners = {}
        self._waiters = {}

    def add(self, name: str, coroutine_function: CoroutineFunctionT) -> None:
        """
        Register a new event callback to a given event name.

        Args:
            name:
                The name of the event to register to.
            coroutine_function:
                The event callback to invoke when this event is fired.
        """
        assertions.assert_that(
            asyncio.iscoroutinefunction(coroutine_function), "You must subscribe a coroutine function only", TypeError
        )
        if name not in self._listeners:
            self._listeners[name] = []
        self._listeners[name].append(coroutine_function)

    def remove(self, name: str, coroutine_function: CoroutineFunctionT) -> None:
        """
        Remove the given coroutine function from the handlers for the given event. The name is mandatory to enable
        supporting registering the same event callback for multiple event types.

        Args:
            name:
                The event to remove from.
            coroutine_function:
                The event callback to remove.
        """
        if name in self._listeners and coroutine_function in self._listeners[name]:
            if len(self._listeners[name]) - 1 == 0:
                del self._listeners[name]
            else:
                self._listeners[name].remove(coroutine_function)

    def dispatch(self, name: str, *args) -> asyncio.Future:
        """
        Dispatch a given event.

        Args:
            name:
                The name of the event to dispatch.
            *args:
                The parameters to pass to the event callback.

        Returns:
            A future. This may be a gathering future of the callbacks to invoke, or it may be
            a completed future object. Regardless, this result will be scheduled on the event loop
            automatically, and does not need to be awaited. Awaiting this future will await
            completion of all invoked event handlers.

            The result either way of awaiting this future will be two values. A set of return values
            and a set of
        """
        if name in self._waiters:
            # Unwrap single or no argument events.
            if len(args) == 1:
                waiter_result_args = args[0]
            elif not args:
                waiter_result_args = None
            else:
                waiter_result_args = args

            for future, predicate in tuple(self._waiters[name].items()):
                try:
                    if predicate(*args):
                        future.set_result(waiter_result_args)
                        del self._waiters[name][future]
                except Exception as ex:
                    future.set_exception(ex)
                    del self._waiters[name][future]

            if not self._waiters[name]:
                del self._waiters[name]

        if name in self._listeners:
            return asyncio.gather(*(callback(*args) for callback in self._listeners[name]))

        return completed_future()

    def wait_for(
        self, name: str, *, timeout: typing.Optional[float], predicate: typing.Callable[..., bool]
    ) -> asyncio.Future:
        """Given an event name, wait for the event to occur once, then return
        the arguments that accompanied the event as the result.

        Events can be filtered using a given predicate function. If unspecified,
        the first event of the given name will be a match.

        Every event that matches the event name that the bot receives will be
        checked. Thus, if you need to wait for events in a specific guild or
        channel, or from a specific person, you want to give a predicate that
        checks this.

        Parameters
        ----------
        name : :obj:`str`
            The name of the event to wait for.
        timeout : :obj:`float`, optional
            The timeout to wait for before cancelling and raising an
            :obj:`asyncio.TimeoutError` instead. If this is `None`, this will
            wait forever. Care must be taken if you use `None` as this may
            leak memory if you do this from an event listener that gets
            repeatedly called. If you want to do this, you should consider
            using an event listener instead of this function.
        predicate :
            A function that takes the arguments for the event and returns True
            if it is a match, or False if it should be ignored.
            This cannot be a coroutine function.

        Returns
        -------
        A future that when awaited will provide a the arguments passed to the
        first matching event. If no arguments are passed to the event, then
        `None` is the result. If one argument is passed to the event, then
        that argument is the result, otherwise a tuple of arguments is the
        result instead.

        Note that awaiting this result will raise an :obj:`asyncio.TimeoutError`
        if the timeout is hit and no match is found. If the predicate throws
        any exception, this is raised immediately.
        """
        future = asyncio.get_event_loop().create_future()
        if name not in self._waiters:
            # This is used as a weakref dict to allow automatically tidying up
            # any future that falls out of scope entirely.
            self._waiters[name] = weakref.WeakKeyDictionary()
        self._waiters[name][future] = predicate
        # noinspection PyTypeChecker
        return asyncio.ensure_future(asyncio.wait_for(future, timeout))


def completed_future(result: typing.Any = None) -> asyncio.Future:
    """
    Create a future on the current running loop that is completed, then return it.

    Args:
        result:
            The value to set for the result of the future.

    Returns:
        The completed future.
    """
    future = asyncio.get_event_loop().create_future()
    future.set_result(result)
    return future


@contextlib.asynccontextmanager
async def maybe_timeout(timeout: type_hints.Nullable[typing.Union[float, int]]):
    """
    Wrapper for :mod:`async_timeout` that may or may not actually wait for a timeout, depending on how it is called.

    This is a :class:`contextlib.AbstractAsyncContextManager`, so must be used in an `async with` block:

    >>> async with maybe_timeout(30):
    ...     await some_slow_task

    Args:
        timeout:
            The timeout to wait for before raising an :class:`asyncio.TimeoutError`. If this is `None`, then this
            will never be raised.
    """
    if timeout is not None and timeout > 0:
        async with async_timeout.timeout(timeout):
            yield
    else:
        yield


__all__ = [
    "optional_await",
    "CoroutineFunctionT",
    "PartialCoroutineProtocolT",
    "EventDelegate",
    "completed_future",
    "maybe_timeout",
]
