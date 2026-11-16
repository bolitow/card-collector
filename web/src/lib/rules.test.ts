import { describe, expect, it } from "vitest";

import vectors from "../../../shared/search-vectors.json";
import { formatCodeList } from "./codes";
import { progress } from "./progress";
import { cardTokens, matches, parseQuery } from "./search";

describe("recherche (F-09, CA-12) — vecteurs partagés avec le serveur", () => {
  for (const { q, expect: expected } of vectors.queries) {
    it(`« ${q} »`, () => {
      const terms = parseQuery(q);
      const found = vectors.cards
        .filter((card) => matches(terms, cardTokens(card.code, card.name, card.group, card.teams)))
        .map((card) => card.id);
      expect(found).toEqual(expected);
    });
  }
});

describe("listes de codes (F-12)", () => {
  it("sépare par des virgules, en ordre naturel", () => {
    expect(formatCodeList(["10", "2", "WK-3", "1"])).toBe("1, 2, 10, WK-3");
  });
  it("regroupe les numéros qui se suivent en format compact", () => {
    const owned = ["1", "2", "3", "5", "9", "10", "11", "WK-3", "001", "002"];
    expect(formatCodeList(owned, true)).toBe("1-3, 001-002, 5, 9-11, WK-3");
  });
});

describe("avancement (RG-15)", () => {
  it("porte sur la base quand les types sont mélangés et qu'une carte de base est possédée", () => {
    expect(progress({ base: 200, insert: 100 }, { base: 50, insert: 10 })).toMatchObject({ owned: 50, total: 200, label: "25 %" });
  });
  it("porte sur toute la série sinon", () => {
    expect(progress({ base: 200, insert: 100 }, { insert: 3 })).toMatchObject({ owned: 3, total: 300, label: "1 %" });
  });
  it("affiche « <1 % » pour une collection entamée, et n'arrondit jamais à 100 %", () => {
    expect(progress({ base: 4042 }, { base: 1 }).label).toBe("<1 %");
    expect(progress({ base: 300 }, { base: 299 }).label).toBe("99 %");
  });
});
