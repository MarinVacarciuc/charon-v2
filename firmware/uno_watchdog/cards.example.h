#pragma once
// TEMPLATE. Copy to cards.h and fill in. cards.h is gitignored.
//
// Two factors, not one (added 2026-09-20). A card UID is "something you have" and is
// clonable by anyone who reads it - anyone who knows one can write it to a blank card, which
// is exactly why this file lives beside secrets.h rather than in the repository. The PIN
// below is "something you know" on top of that: a short sequence pressed on the board's own
// four buttons (see uno_watchdog.ino) after a correct tap, unique per card rather than one
// secret shared by everyone who carries a badge.
//
// PIN entries are BUTTON INDEXES (0-3, matching BTN1-BTN4 wired to A0-A3), not digits typed
// on a numeric pad - this board has four buttons, not twelve. Agree the sequence with the
// cardholder yourself; it is not something the reader can print out for you the way a UID is.
//
// To find a card's UID: flash this sketch, open the serial monitor at 9600, pull the
// heartbeat wire so the board goes into failover, and tap the card. Unknown cards are
// refused and their UID is printed, which is the enrolment path.

struct CharonCard {
  const char *uid;
  const char *holder;
  const uint8_t *pin;
  uint8_t pinLen;
};

// static const uint8_t MARIN_PIN[] = {2, 0, 3, 1};
static const CharonCard CHARON_CARDS[] = {
  // {"DE AD BE EF", "Marin", MARIN_PIN, 4},
};
static const int CHARON_CARD_COUNT = sizeof(CHARON_CARDS) / sizeof(CHARON_CARDS[0]);
