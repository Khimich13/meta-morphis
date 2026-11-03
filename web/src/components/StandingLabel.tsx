import {
  type CardProgress,
  cardStanding,
  MASTERED_LEVEL,
  shownLevel,
  standingDetails,
} from '../lib/progress';

/**
 * How an answer just changed the pips, to animate it (see App.css):
 *   up   - one more pip painted green
 *   down - the last green pip unpainted
 *   miss - wrong, but no pip to take away: the pips flash red and shake
 */
export type PipChange = 'up' | 'down' | 'miss';

/**
 * A card's level as pips, e.g. "●●○", with the word "Mastered" once all
 * are filled - see cardStanding in lib/progress.ts. A card never answered
 * has empty pips, like one just missed: neither is known yet. Screen
 * readers hear it in full, and a mouse shows the level as a tooltip.
 */
export default function StandingLabel({
  record,
  change = null,
}: {
  record: CardProgress | undefined;
  /** How the last answer changed the pips, to animate; null for none */
  change?: PipChange | null;
}) {
  const standing = cardStanding(record);
  const details = standingDetails(record);
  const mastered = standing === 'mastered';
  return (
    <span
      className={`label standing ${standing}`}
      role="img"
      aria-label={mastered ? `Mastered, ${details}` : details}
      title={details}
    >
      {mastered && (
        <span className={change === 'up' ? 'name appear' : 'name'}>Mastered</span>
      )}
      <Pips level={shownLevel(record)} change={change} />
    </span>
  );
}

/** One pip per step to mastered, filled up to the card's level */
function Pips({ level, change }: { level: number; change: PipChange | null }) {
  return (
    <span className={change === 'miss' ? 'pips missed' : 'pips'}>
      {Array.from({ length: MASTERED_LEVEL }, (_, i) => {
        let name = i < level ? 'on' : '';
        // The pip that was just painted, or the one just unpainted
        if (change === 'up' && i === level - 1) name += ' painted';
        if (change === 'down' && i === level) name += ' unpainted';
        return <span key={i} className={name} />;
      })}
    </span>
  );
}
