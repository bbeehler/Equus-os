export interface BookingContext {
  distanceKm: number;
  horsesBookedAtSameBarnSameDay: number;
}

/**
 * Calculates the travel fee based on business rules:
 * - Inside 30km: $0.00
 * - Outside 30km: $0.73/km on the excess distance
 * - 3 or more horses at same barn on same day: $0.00 (Waived)
 */
export function calculateTravelFee(context: BookingContext): {
  travelFee: number;
  isWaived: boolean;
  reason: string;
} {
  // Rule 1: Group booking of 3+ horses waives the fee entirely
  if (context.horsesBookedAtSameBarnSameDay >= 3) {
    return {
      travelFee: 0,
      isWaived: true,
      reason: 'Group Booking Incentive (3+ Horses: Fee Waived)',
    };
  }

  // Rule 2: Free local radius within 30km
  if (context.distanceKm <= 30) {
    return {
      travelFee: 0,
      isWaived: true,
      reason: 'Within Free 30km Home Base Radius',
    };
  }

  // Rule 3: Standard $0.73/km on distance beyond 30km
  const billableKm = context.distanceKm - 30;
  const travelFee = Math.round(billableKm * 0.73 * 100) / 100;

  return {
    travelFee,
    isWaived: false,
    reason: `Standard Mileage (${billableKm.toFixed(1)} km @ $0.73/km)`,
  };
}