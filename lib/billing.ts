export interface HorseBillingProfile {
  is_flagship_barn: boolean;
  is_marketing_tier: boolean; // 3 promo horses
  minutes_used_this_month: number;
}

export function calculateSessionFee(
  durationMinutes: number,
  horse: HorseBillingProfile
): { fee: number; updatedTotalMinutes: number; note: string } {
  const previousMinutes = horse.minutes_used_this_month;
  const newTotalMinutes = previousMinutes + durationMinutes;

  // Non-flagship barns: $2.00/min or $60 for standard 20-min session
  if (!horse.is_flagship_barn) {
    return {
      fee: durationMinutes === 20 ? 60 : durationMinutes * 2.0,
      updatedTotalMinutes: newTotalMinutes,
      note: 'Standard Mobile Rate ($2.00/min)',
    };
  }

  // Flagship Marketing Tier (3 Promo Horses): First 200 mins free, then $1.00/min
  if (horse.is_marketing_tier) {
    if (newTotalMinutes <= 200) {
      return {
        fee: 0,
        updatedTotalMinutes: newTotalMinutes,
        note: 'Promo Allowance (100% Free)',
      };
    }
    const billableMinutes = previousMinutes >= 200 ? durationMinutes : newTotalMinutes - 200;
    return {
      fee: billableMinutes * 1.0,
      updatedTotalMinutes: newTotalMinutes,
      note: 'Marketing Tier Overage ($1.00/min)',
    };
  }

  // Flagship Standard Tier (9 Horses): Baseline <= 200 mins @ $1.00/min, overage @ $2.00/min
  if (previousMinutes >= 200) {
    return {
      fee: durationMinutes * 2.0,
      updatedTotalMinutes: newTotalMinutes,
      note: 'Standard Tier Overage ($2.00/min)',
    };
  }

  if (newTotalMinutes <= 200) {
    return {
      fee: durationMinutes * 1.0,
      updatedTotalMinutes: newTotalMinutes,
      note: 'Standard Tier Baseline ($1.00/min)',
    };
  }

  const baselineMinutes = 200 - previousMinutes;
  const overageMinutes = newTotalMinutes - 200;
  const fee = baselineMinutes * 1.0 + overageMinutes * 2.0;

  return {
    fee,
    updatedTotalMinutes: newTotalMinutes,
    note: 'Standard Tier (Mixed Baseline & Overage Rate)',
  };
}