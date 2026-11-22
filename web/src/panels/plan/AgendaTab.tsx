/** The agenda: what the clock will do in this project, day by day, and what each event leads to. */
import { CalendarClock } from "lucide-react";
import { get } from "../../api/client";
import { ErrorNote } from "../../components/common";
import { Empty, Loading } from "../kit";
import { groupByDay } from "../../desk/logic";
import { formatDateTime, formatTime } from "../../lib/format";
import { useLoad } from "../../lib/useLoad";
import { t } from "../../strings";
import { AgentText } from "../board/parts";
import type { TabProps } from "../memory/parts";

const dayFormat = new Intl.DateTimeFormat(undefined, { dateStyle: "full" });

export function AgendaTab({ projectId, changes }: Pick<TabProps, "projectId" | "changes">): JSX.Element {
  const words = t.decisions.agenda;
  const agenda = useLoad(() => get("/v1/agenda/show", { project_id: projectId }), [projectId, changes]);
  if (!agenda.data) return agenda.error ? <ErrorNote error={agenda.error} /> : <Loading />;
  const { next_wake: nextWake, lines, timezone } = agenda.data;
  return (
    <>
      <p className="record-text" data-testid="next-wake">
        {nextWake ? words.nextWake(formatDateTime(nextWake)) : words.noWake}
      </p>
      <p className="quiet">{words.timezone(timezone)}</p>
      {lines.length === 0 ? <Empty icon={CalendarClock} title={words.emptyTitle} next={words.emptyNext} /> : null}
      {groupByDay(lines).map((group) => {
        const day = dayFormat.format(group.date);
        return (
          <section key={group.day} className="agenda-day" aria-labelledby={`agenda-${group.day}`} data-testid="agenda-day">
            <h3 className="group-title" id={`agenda-${group.day}`}>
              {day}
            </h3>
            <ul className="records plain" aria-label={words.dayLabel(day)}>
              {group.lines.map((line, index) => (
                <li key={index} data-testid="agenda-line">
                  <time dateTime={line.at}>{formatTime(line.at)}</time>
                  <div>
                    <p className="record-text">
                      <AgentText text={line.what} />
                    </p>
                    <p className="quiet">
                      <AgentText text={line.consequence} />
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          </section>
        );
      })}
    </>
  );
}
