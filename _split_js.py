from pathlib import Path

root = Path(__file__).resolve().parent / "static" / "js"


def write(path, text):
    if not text.endswith("\n"):
        text += "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    print(f"{text.count(chr(10)):4} {path.relative_to(root).as_posix()}")


src = (root / "features/arcade/controller.js").read_text(encoding="utf-8").splitlines()
write(root / "features/arcade/controller/shell.js", "\n".join([
    'import { byId, setText } from "../../../utils/format.js";',
    'import { showToast } from "../../../views/dialogs.js";',
    "",
    "export class ArcadeCore {",
    *src[7:115],
    "}",
    "",
]))
write(root / "features/arcade/controller/playback.js", "\n".join([
    'import { setText } from "../../../utils/format.js";',
    "",
    "export const PlaybackMixin = (Base) => class extends Base {",
    *src[116:189],
    "};",
    "",
]))
write(root / "features/arcade/controller/index.js", "\n".join([
    'import { AudioMixin } from "../audio.js";',
    'import { ParticlesMixin } from "../particles.js";',
    'import { ReelsMixin } from "../reels.js";',
    'import { PlaybackMixin } from "./playback.js";',
    'import { ArcadeCore } from "./shell.js";',
    "",
    "export const ArcadeSensoryController = ParticlesMixin(ReelsMixin(AudioMixin(PlaybackMixin(ArcadeCore))));",
    "export let arcadeSensory = null;",
    "export function startArcade() {",
    "  arcadeSensory = new ArcadeSensoryController();",
    "}",
    "",
]))
(root / "features/arcade/controller.js").unlink()

src = (root / "features/voice/device.js").read_text(encoding="utf-8").splitlines()
write(root / "features/voice/device/devices.js", "\n".join([
    'import { S, audioInputStorageKey, audioOutputStorageKey } from "../../../store/state.js";',
    'import { byId } from "../../../utils/format.js";',
    "",
    *src[6:116],
    "",
]))
write(root / "features/voice/device/connect.js", "\n".join([
    'import { request } from "../../../api/client.js";',
    'import { S, audioInputStorageKey, audioOutputStorageKey } from "../../../store/state.js";',
    'import { byId } from "../../../utils/format.js";',
    'import { showToast } from "../../../views/dialogs.js";',
    'import { startMicrophoneTest, stopMicrophoneTest, testAudioOutput } from "../testing.js";',
    'import { applyVoiceAudioDevices, refreshAudioDevices, routeTestAudio, setMicLevel } from "./devices.js";',
    "",
    *src[117:195],
    "",
]))
write(root / "features/voice/device/index.js", "\n".join([
    "export {",
    "  applyVoiceAudioDevices,",
    "  populateAudioSelect,",
    "  refreshAudioDevices,",
    "  resolveTwilioDeviceId,",
    "  routeTestAudio,",
    "  setMicLevel,",
    "  twilioDeviceEntries,",
    "  twilioHasDevice,",
    "  waitForTwilioAudioDevices,",
    '} from "./devices.js";',
    'export { bindVoice, createVoiceDevice } from "./connect.js";',
    "",
]))
(root / "features/voice/device.js").unlink()

src = (root / "views/call-stage.js").read_text(encoding="utf-8").splitlines()
stage = "\n".join(src[0:133])
stage = stage.replace("../features/", "../../features/")
stage = stage.replace("../store/", "../../store/")
stage = stage.replace("../utils/", "../../utils/")
stage = stage.replace("../../features/arcade/controller.js", "../../features/arcade/controller/index.js")
write(root / "views/call-stage/stage.js", stage + "\n")
write(root / "views/call-stage/timer.js", "\n".join([
    'import { S, state } from "../../store/state.js";',
    "",
    *src[134:154],
    "",
]))
write(root / "views/call-stage/index.js", "\n".join([
    'export { renderCallStage } from "./stage.js";',
    'export { startCallTimer, stopCallTimer } from "./timer.js";',
    "",
]))
(root / "views/call-stage.js").unlink()

src = (root / "views/prospects-table.js").read_text(encoding="utf-8").splitlines()
write(root / "views/prospects-table/query.js", "\n".join([
    'import { S, selectedLeadIds, state } from "../../store/state.js";',
    'import { byId } from "../../utils/format.js";',
    "",
    *src[6:44],
    "",
]))
write(root / "views/prospects-table/rows.js", "\n".join([
    'import { changeLeadStatus } from "../../controllers/prospects.js";',
    'import { S, selectedLeadIds, state } from "../../store/state.js";',
    'import { STATUS_LABELS, STATUS_STYLES, initials } from "../../utils/format.js";',
    'import { formatPhoneNumber } from "../../utils/phone.js";',
    'import { openTranscript } from "../../utils/transcript.js";',
    'import { renderTable } from "./render.js";',
    "",
    "export function appendLeadRows(body, leads, extras) {",
    *src[86:181],
    "}",
    "",
]))
write(root / "views/prospects-table/render.js", "\n".join([
    'import { S, selectedLeadIds, state } from "../../store/state.js";',
    'import { byId, setText } from "../../utils/format.js";',
    'import { appendLeadRows } from "./rows.js";',
    'import { crmTableSignature, filteredLeads, importedColumns } from "./query.js";',
    "",
    "export function renderTable() {",
    *src[46:85],
    "  appendLeadRows(body, leads, extras);",
    *src[182:195],
    "}",
    "",
]))
write(root / "views/prospects-table/index.js", "\n".join([
    'export { crmTableSignature, filteredLeads, importedColumns } from "./query.js";',
    'export { renderTable } from "./render.js";',
    "",
]))
(root / "views/prospects-table.js").unlink()

replacements = {
    'from "../features/arcade/controller.js"': 'from "../features/arcade/controller/index.js"',
    'from "./features/arcade/controller.js"': 'from "./features/arcade/controller/index.js"',
    'from "../features/voice/device.js"': 'from "../features/voice/device/index.js"',
    'from "./features/voice/device.js"': 'from "./features/voice/device/index.js"',
    'from "./device.js"': 'from "./device/devices.js"',
    'from "./call-stage.js"': 'from "./call-stage/index.js"',
    'from "./prospects-table.js"': 'from "./prospects-table/index.js"',
    'from "../views/prospects-table.js"': 'from "../views/prospects-table/index.js"',
}
for path in root.rglob("*.js"):
    text = path.read_text(encoding="utf-8")
    updated = text
    for old, new in replacements.items():
        updated = updated.replace(old, new)
    if updated != text:
        path.write_text(updated, encoding="utf-8", newline="\n")
        print("updated", path.relative_to(root).as_posix())
