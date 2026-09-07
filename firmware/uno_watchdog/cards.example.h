#pragma once
// TEMPLATE. Copy to cards.h and fill in. cards.h is gitignored.
//
// A card UID is a credential, not a serial number: anyone who knows one can write it to a
// blank card. That is precisely the weakness of "something you have" as a factor, and it is
// why these live beside secrets.h rather than in the repository.
//
// To find a card's UID: flash this sketch, open the serial monitor at 9600, pull the
// heartbeat wire so the board goes into failover, and tap the card. Unknown cards are
// refused and their UID is printed, which is the enrolment path.

struct CharonCard { const char *uid; const char *holder; };

static const CharonCard CHARON_CARDS[] = {
  // {"DE AD BE EF", "Marin"},
};
static const int CHARON_CARD_COUNT = sizeof(CHARON_CARDS) / sizeof(CHARON_CARDS[0]);
