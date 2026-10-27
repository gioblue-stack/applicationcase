import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { actionLink, localScreen, phonesFor, telOf, visibleRiskQuestions } from "./help";
import type { Bootstrap } from "./types";

const read = (path: string) => JSON.parse(readFileSync(new URL(`../../../../content/${path}`, import.meta.url), "utf8"));
const content = {
  help_phones: read("help_phones.json"),
  suicide_block: read("instruments/suicide_block.ru.v1.json"),
} as Bootstrap;

describe("phonesFor", () => {
  it("always shows 112 and the federal helpline, then the region — as the server does", () => {
    expect(phonesFor(content.help_phones, "moscow").map((p) => p.id)).toEqual(["112", "8-800-100-49-94", "msk-051"]);
    expect(phonesFor(content.help_phones, null).map((p) => p.id)).toEqual(["112", "8-800-100-49-94"]);
  });
});

describe("help screen actions", () => {
  const screen = localScreen(content, "emergency", null);

  it("turns every emergency action into a call", () => {
    const contacts = [{ name: "Сестра", phone: "+7 (900) 000-00-99" }];
    expect(screen.actions.map((a) => actionLink(a, screen, contacts)?.href)).toEqual([
      "tel:112", "tel:88001004994", "tel:+79000000099"]);
  });

  it("hides «call a close person» when the safety plan has no phone", () => {
    const trusted = screen.actions.find((a) => a.action === "call_trusted_contact")!;
    expect(actionLink(trusted, screen, [{ name: "Друг", phone: null }])).toBeNull();
  });

  it("keeps only digits and plus in tel links", () => {
    expect(telOf("+7 495 989-50-50")).toBe("+74959895050");
  });
});

describe("visibleRiskQuestions", () => {
  const questions = content.suicide_block.questions;

  it("asks method, intent and plan only after «yes» to active thoughts", () => {
    expect(visibleRiskQuestions(questions, {}).map((q) => q.id)).toEqual(["q1", "q2", "q6"]);
    expect(visibleRiskQuestions(questions, { q2: false }).map((q) => q.id)).toEqual(["q1", "q2", "q6"]);
    expect(visibleRiskQuestions(questions, { q2: true }).map((q) => q.id)).toEqual(["q1", "q2", "q3", "q4", "q5", "q6"]);
  });
});
