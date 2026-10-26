import {
  type CardProgress,
  cardStanding,
  STANDING_LABELS,
  standingDetails,
} from '../lib/progress';

/**
 * A card's standing with the numbers behind it, e.g. "Fair · 3/6" for 3
 * of 6 answered right, or just "New" - see cardStanding in
 * lib/progress.ts. Screen readers hear it in full, and a mouse shows the
 * full description as a tooltip.
 */
export default function StandingLabel({ record }: { record: CardProgress | undefined }) {
  const standing = cardStanding(record);
  const name = STANDING_LABELS[standing];
  const details = standingDetails(record);
  const numbers =
    record === undefined ? '' : ` · ${record.right}/${record.right + record.wrong}`;
  return (
    <span
      className={`label standing ${standing}`}
      role="img"
      aria-label={`${name}: ${details}`}
      title={details}
    >
      {name}
      {numbers}
    </span>
  );
}
