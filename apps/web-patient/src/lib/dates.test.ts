import { describe, expect, it } from "vitest";
import { dayLabel } from "./dates";

describe("dayLabel", () => {
  it("says today and tomorrow in words", () => {
    expect(dayLabel("2026-10-27", "2026-10-27")).toBe("сегодня");
    expect(dayLabel("2026-10-28", "2026-10-27")).toBe("завтра");
  });

  it("names later days with the month, across month and year ends", () => {
    expect(dayLabel("2026-11-02", "2026-10-27")).toBe("2 ноября");
    expect(dayLabel("2026-11-01", "2026-10-31")).toBe("завтра");
    expect(dayLabel("2027-01-05", "2026-12-31")).toBe("5 января");
  });
});
