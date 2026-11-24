/** The keyboard shortcuts, shown with "?" from anywhere. */
import { shell } from "../strings.shell";
import { Sheet } from "../ui/Sheet";

const isMac = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform);

export function Shortcuts({ onClose }: { onClose(): void }): JSX.Element {
  const mod = isMac ? "⌘" : "Ctrl";
  const rows: [string[], string][] = [
    [[mod, "K"], shell.keys.palette],
    [["G", "H"], shell.keys.home],
    [["G", "P"], shell.keys.projects],
    [["G", "S"], shell.keys.settings],
    [["G", "C"], shell.keys.chat],
    [["G", "O"], shell.keys.overview],
    [["G", "W"], shell.keys.work],
    [["G", "R"], shell.keys.squad],
    [["G", "D"], shell.keys.deliverables],
    [["Enter"], shell.keys.send],
    [["Shift", "Enter"], shell.keys.newline],
    [["↑"], shell.keys.lastMessage],
    [["Esc"], shell.keys.escape],
    [["?"], shell.keys.help],
  ];
  return (
    <Sheet title={shell.keys.title} onClose={onClose} size="md" testId="shortcuts">
      <table className="grid shortcuts">
        <caption className="visually-hidden">{shell.keys.title}</caption>
        <tbody>
          {rows.map(([keys, what]) => (
            <tr key={what}>
              <td>{what}</td>
              <td className="num">
                {keys.map((key, index) => (
                  <span key={key}>
                    {index > 0 ? <span className="quiet"> {keys[0] === "G" ? shell.keys.then : "+"} </span> : null}
                    <kbd>{key}</kbd>
                  </span>
                ))}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="quiet">{shell.keys.note}</p>
    </Sheet>
  );
}
