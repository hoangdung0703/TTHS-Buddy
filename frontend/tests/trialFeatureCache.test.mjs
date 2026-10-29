// Unit tests for src/lib/trialFeatureCache.ts (per-user feature probe memory). Node's built-in runner.
import assert from "node:assert/strict";
import { test } from "node:test";

import { createTrialFeatureCache } from "../src/lib/trialFeatureCache.ts";

// A fake auth + backend: `user` is who is signed in, `allowed` the emails' ids the backend lets in.
function setup({ allowed = ["A"], failNext = 0 } = {}) {
  const world = { user: null, allowed: new Set(allowed), probes: [], failNext };
  const cache = createTrialFeatureCache({
    currentUser: async () => (world.user ? { id: world.user, token: `token-${world.user}` } : null),
    probe: async (token) => {
      world.probes.push(token);
      if (world.failNext > 0) {
        world.failNext--;
        throw new TypeError("Failed to fetch");
      }
      return world.allowed.has(token.slice("token-".length)) ? "enabled" : "disabled";
    }
  });
  const seen = [];
  cache.subscribe((status) => seen.push(status));
  return { world, cache, seen };
}

test("no probe without a token", async () => {
  const { world, cache } = setup();
  assert.equal(await cache.probe(), "unknown");
  assert.equal(world.probes.length, 0);
  assert.equal(cache.getStatus(), "unknown");
});

test("signing in after a signed-out probe: the allowed user gets enabled", async () => {
  const { world, cache, seen } = setup();
  await cache.probe(); // on the login page: nothing sent, nothing kept
  world.user = "A";
  cache.setUser("A");
  assert.equal(await cache.probe(), "enabled");
  assert.deepEqual(world.probes, ["token-A"]);
  assert.deepEqual(seen, ["enabled"]);
});

test("one probe per user, even with concurrent callers", async () => {
  const { world, cache } = setup();
  world.user = "A";
  const results = await Promise.all([cache.probe(), cache.probe(), cache.probe()]);
  assert.deepEqual(results, ["enabled", "enabled", "enabled"]);
  assert.equal(await cache.probe(), "enabled");
  assert.equal(world.probes.length, 1);
});

test("account switch without reload: A allowed -> B not allowed -> A again", async () => {
  const { world, cache, seen } = setup({ allowed: ["A"] });
  world.user = "A";
  assert.equal(await cache.probe(), "enabled");
  world.user = null;
  cache.setUser(null); // sign-out
  assert.equal(cache.getStatus(), "unknown");
  world.user = "B";
  cache.setUser("B");
  assert.equal(await cache.probe(), "disabled");
  world.user = "A";
  cache.setUser("A");
  assert.equal(await cache.probe(), "enabled");
  assert.deepEqual(world.probes, ["token-A", "token-B", "token-A"]);
  assert.deepEqual(seen, ["enabled", "unknown", "disabled", "unknown", "enabled"]);
});

test("account switch the other way: B not allowed -> A allowed", async () => {
  const { world, cache } = setup({ allowed: ["A"] });
  world.user = "B";
  assert.equal(await cache.probe(), "disabled");
  world.user = "A";
  // Even without an explicit setUser, the next probe notices the different user.
  assert.equal(await cache.probe(), "enabled");
});

test("a network error is not kept: the next call probes again", async () => {
  const { world, cache } = setup({ failNext: 1 });
  world.user = "A";
  assert.equal(await cache.probe(), "unknown");
  assert.equal(cache.getStatus(), "unknown");
  assert.equal(await cache.probe(), "enabled");
  assert.equal(world.probes.length, 2);
});

test("an answer that arrives after an account switch is dropped", async () => {
  let release;
  const gate = new Promise((resolve) => (release = resolve));
  const world = { user: "A" };
  const cache = createTrialFeatureCache({
    currentUser: async () => (world.user ? { id: world.user, token: world.user } : null),
    probe: async (token) => {
      if (token === "A") await gate;
      return "enabled";
    }
  });
  const first = cache.probe();
  await new Promise((resolve) => setTimeout(resolve, 0));
  world.user = "B";
  cache.setUser("B");
  release();
  assert.equal(await first, "unknown");
  assert.equal(cache.getStatus(), "unknown");
  assert.equal(cache.getUserId(), "B");
});

test("remember: what a trial request learned applies to the user who made it", () => {
  const { cache } = setup();
  cache.remember("disabled", null); // no user: ignored
  assert.equal(cache.getStatus(), "unknown");
  cache.remember("enabled", "A");
  assert.equal(cache.getStatus(), "enabled");
  cache.remember("disabled", "B"); // a different user's answer replaces A's
  assert.equal(cache.getUserId(), "B");
  assert.equal(cache.getStatus(), "disabled");
});
