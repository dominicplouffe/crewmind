/** Standing orders: add one, confirm, edit or discard a proposed one, retire one in force. */
import { useState } from "react";
import { get, post, type Order } from "../../api/client";
import { Empty, ErrorNote, Loading } from "../../components/common";
import { useLoad } from "../../lib/useLoad";
import { t } from "../../strings";
import { ServerNote, Tag, TextForm, stateName, useAct, type TabProps } from "./parts";

export function OrdersTab({ projectId, changes, onChanged }: TabProps): JSX.Element {
  const orders = useLoad(() => get("/v1/orders/list", { project_id: projectId }), [projectId, changes]);
  const [editing, setEditing] = useState<number | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const act = useAct(() => {
    orders.reload();
    onChanged();
  });
  const items = orders.data?.items ?? [];
  const words = t.memory.orders;

  const change = (work: () => Promise<Order>): Promise<boolean> =>
    act.run(async () => {
      setNote((await work()).note ?? null);
    });
  const ref = (order: Order): { project_id: string; order_id: number } => ({ project_id: projectId, order_id: order.id });

  return (
    <>
      <TextForm
        label={words.addLabel}
        submit={words.add}
        onSubmit={async (text) => {
          const order = await post("/v1/orders/pin", { project_id: projectId, what: text });
          setNote(order.note ?? null);
          orders.reload();
          onChanged();
        }}
      />
      <ServerNote text={note} />
      <ErrorNote error={orders.error} />
      <ErrorNote error={act.error} />
      {orders.loading && !orders.data ? <Loading /> : null}
      {orders.data && items.length === 0 ? <Empty title={words.emptyTitle} next={words.emptyNext} /> : null}
      <ul className="records plain" aria-label={words.listLabel}>
        {items.map((order) => (
          <li key={order.id} data-testid="order" className={order.state === "retired" ? "is-past" : ""}>
            <p className="record-text">{order.text}</p>
            <p className="quiet">
              <Tag>{stateName(words.states, order.state)}</Tag> {words.by(order.proposed_by)}
              {order.being_shortened ? ` · ${words.shortening}` : ""}
            </p>
            {editing === order.id ? (
              <TextForm
                label={words.editLabel(order.id)}
                submit={words.confirmEdited}
                initial={order.text}
                multiline
                focus
                onCancel={() => setEditing(null)}
                onSubmit={async (text) => {
                  const result = await post("/v1/orders/confirm", { ...ref(order), text });
                  setNote(result.note ?? null);
                  setEditing(null);
                  orders.reload();
                  onChanged();
                }}
              />
            ) : (
              <div className="row wrap">
                {order.state === "proposed" ? (
                  <>
                    <button
                      type="button"
                      className="button small primary"
                      disabled={act.busy}
                      onClick={() => void change(() => post("/v1/orders/confirm", ref(order)))}
                    >
                      {t.listening.confirm}
                      <span className="visually-hidden"> {t.listening.orderOf(order.id)}</span>
                    </button>
                    <button type="button" className="button small" onClick={() => setEditing(order.id)}>
                      {t.listening.edit}
                      <span className="visually-hidden"> {t.listening.orderOf(order.id)}</span>
                    </button>
                    <button
                      type="button"
                      className="button small"
                      disabled={act.busy}
                      onClick={() => void change(() => post("/v1/orders/discard", ref(order)))}
                    >
                      {t.listening.discard}
                      <span className="visually-hidden"> {t.listening.orderOf(order.id)}</span>
                    </button>
                  </>
                ) : null}
                {order.state === "active" ? (
                  <button
                    type="button"
                    className="button small"
                    disabled={act.busy}
                    onClick={() => void change(() => post("/v1/orders/retire", ref(order)))}
                  >
                    {words.retire}
                    <span className="visually-hidden"> {t.listening.orderOf(order.id)}</span>
                  </button>
                ) : null}
              </div>
            )}
          </li>
        ))}
      </ul>
    </>
  );
}
