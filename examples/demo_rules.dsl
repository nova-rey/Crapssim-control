WHEN point_on AND bets.6 == 0 THEN place_bet(number=6, amount=12)
WHEN point_on AND bets.8 == 0 THEN place_bet(number=8, amount=12)
WHEN NOT point_on THEN line_bet(side=pass, amount=10)
