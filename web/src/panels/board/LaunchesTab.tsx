/** Side effects and launches: what agents did outside the project, and the watch on each launch. */
import { useState } from "react";
import { get, post } from "../../api/client";
import { Empty, ErrorNote, Loading, Pre } from "../../components/common";
import { useLoad } from "../../lib/useLoad";
import { t } from "../../strings";
import { useAct } from "../memory/parts";
import { AgentText, Bar, StateTag, type BoardTabProps } from "./parts";

interface Props extends BoardTabProps {
  onChanged(): void;
}

export function LaunchesTab({ projectId, changes, onChanged }: Props): JSX.Element {
  const launches = useLoad(() => get("/v1/launches/list", { project_id: projectId }), [projectId, changes]);
  const [confirming, setConfirming] = useState<number | null>(null);
  const act = useAct(() => {
    setConfirming(null);
    launches.reload();
    onChanged();
  });
  const items = launches.data?.items ?? [];
  const words = t.board.launches;

  return (
    <>
      <Bar onRefresh={launches.reload} busy={launches.loading} />
      <ErrorNote error={launches.error} />
      <ErrorNote error={act.error} />
      {launches.loading && !launches.data ? <Loading /> : null}
      {launches.data && items.length === 0 ? <Empty title={words.emptyTitle} next={words.emptyNext} /> : null}
      <ul className="records plain" aria-label={words.listLabel}>
        {items.map((effect) => (
          <li key={effect.id} data-testid="launch" className={effect.state === "retired" ? "is-past" : ""}>
            <p className="record-text">
              <AgentText text={effect.what} />
            </p>
            <p className="quiet row wrap">
              <span className="marker" data-testid="launch-kind">
                {effect.launch ? words.launch : words.effect}
              </span>
              <StateTag state={effect.state} />
              {effect.launch ? (
                <span className={`marker watch-${effect.watch ?? "none"}`} data-testid="launch-watch">
                  {effect.watch ? words.watch(effect.watch) : words.noWatch}
                </span>
              ) : null}
            </p>
            <p className="quiet">
              {words.by(effect.by)} {words.key(effect.declared_as)} ·{" "}
              {effect.fired === true ? words.fired.yes : effect.fired === false ? words.fired.no : words.fired.unknown}
            </p>
            {effect.outcome ? (
              <p>
                {words.outcome}: <AgentText text={effect.outcome} />
              </p>
            ) : null}
            {effect.launch && effect.watch_result ? (
              <>
                <p className="quiet">{words.watchResult}</p>
                <Pre className="check-output">{effect.watch_result}</Pre>
              </>
            ) : null}
            {effect.launch && effect.state === "finished" ? (
              confirming === effect.id ? (
                <div className="note" role="group" aria-label={words.retireSure}>
                  <p>{words.retireSure}</p>
                  <div className="row wrap">
                    <button
                      type="button"
                      className="button small primary"
                      disabled={act.busy}
                      onClick={() => void act.run(() => post("/v1/launches/retire", { project_id: projectId, effect_id: effect.id }))}
                    >
                      {words.retireYes}
                    </button>
                    <button type="button" className="button small" onClick={() => setConfirming(null)}>
                      {t.common.cancel}
                    </button>
                  </div>
                </div>
              ) : (
                <button type="button" className="button small" onClick={() => setConfirming(effect.id)}>
                  {words.retire}
                  <span className="visually-hidden"> {words.retireOf(effect.what)}</span>
                </button>
              )
            ) : null}
          </li>
        ))}
      </ul>
    </>
  );
}
