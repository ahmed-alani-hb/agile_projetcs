// Realtime, with a fallback that assumes it will sometimes not work.
//
// frappe-ui's initSocket dials the socket.io process directly and derives
// `protocol = port ? 'http' : 'https'`, so in production it always tries HTTPS
// on the site origin. That needs nginx to proxy /socket.io, and it breaks
// outright on an HTTP-only site. Rather than let the feature die silently, we
// watch the connection and fall back to polling when it never arrives.

import { onUnmounted, ref } from 'vue'
import { initSocket } from 'frappe-ui'

// How long to wait for a connection before deciding we are on our own.
const CONNECT_GRACE_MS = 5000
// How often to poll once we have given up on the socket.
const POLL_INTERVAL_MS = 20000
const RECONNECT_ATTEMPTS = 5

export const socketConnected = ref(false)
// Set once the client has stopped trying, so pollers know this is permanent
// rather than a blip worth waiting out.
export const socketUnavailable = ref(false)

let socket = null
let initialised = false

export function getSocket() {
  if (initialised) return socket
  initialised = true
  try {
    socket = initSocket({ port: window.socketio_port })
  } catch (error) {
    // No socket.io at all — polling carries the app.
    socketUnavailable.value = true
    return null
  }

  // Default socket.io retries forever, which means an endless console of
  // failures on a site that will never serve the socket.
  try {
    socket.io.reconnectionAttempts(RECONNECT_ATTEMPTS)
    socket.io.reconnectionDelayMax(10000)
  } catch (error) {
    // Older client without these setters; the listeners below still apply.
  }

  socket.on('connect', () => {
    socketConnected.value = true
    socketUnavailable.value = false
  })
  socket.on('disconnect', () => (socketConnected.value = false))
  socket.on('reconnect_failed', () => {
    socketConnected.value = false
    socketUnavailable.value = true
    try {
      socket.close()
    } catch (error) {
      /* already gone */
    }
  })
  return socket
}

/** Subscribe to a realtime event for the lifetime of the calling component. */
export function useRealtime(event, handler) {
  const active = getSocket()
  if (!active) return
  active.on(event, handler)
  onUnmounted(() => active.off(event, handler))
}

/**
 * Join a document's realtime room, following a changing target.
 *
 * Frappe scopes `publish_realtime(..., doctype=, docname=)` to a room the
 * client has to opt into, so without this a comment published on the server
 * never reaches the open thread.
 */
export function useDocRoom(getTarget) {
  const active = getSocket()
  if (!active) return () => {}

  let current = null

  function leave() {
    if (current) {
      active.emit('doc_unsubscribe', current.doctype, current.name)
      current = null
    }
  }

  function join() {
    const target = getTarget()
    if (
      current &&
      target &&
      current.doctype === target.doctype &&
      current.name === target.name
    ) {
      return
    }
    leave()
    if (target?.doctype && target?.name) {
      active.emit('doc_subscribe', target.doctype, target.name)
      current = { ...target }
    }
  }

  // Rejoin after a reconnect, or the room is silently lost.
  active.on('connect', join)
  onUnmounted(() => {
    leave()
    active.off('connect', join)
  })
  return join
}

/**
 * Keep something fresh whichever transport is available.
 *
 * Always refetches when the tab becomes visible again — cheap, and it covers a
 * laptop reopened after lunch. Additionally polls, but only once the socket has
 * had its grace period and failed, so a healthy socket costs nothing.
 */
export function useLiveRefresh(refetch) {
  getSocket()

  let timer = null

  function startPolling() {
    if (timer) return
    timer = setInterval(refetch, POLL_INTERVAL_MS)
  }

  function stopPolling() {
    if (timer) {
      clearInterval(timer)
      timer = null
    }
  }

  const grace = setTimeout(() => {
    if (!socketConnected.value) startPolling()
  }, CONNECT_GRACE_MS)

  // A socket that connects late should stop the polling it triggered.
  const active = getSocket()
  const onConnect = () => stopPolling()
  const onDrop = () => startPolling()
  if (active) {
    active.on('connect', onConnect)
    active.on('disconnect', onDrop)
  } else {
    startPolling()
  }

  function onVisible() {
    if (document.visibilityState === 'visible') refetch()
  }
  document.addEventListener('visibilitychange', onVisible)

  onUnmounted(() => {
    clearTimeout(grace)
    stopPolling()
    document.removeEventListener('visibilitychange', onVisible)
    if (active) {
      active.off('connect', onConnect)
      active.off('disconnect', onDrop)
    }
  })
}
