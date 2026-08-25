extends RefCounted
class_name WavLoader
## Runtime PCM WAV loader for external beat audio (not imported).

static func load_buffer(bytes: PackedByteArray, label: String = "buffer") -> AudioStreamWAV:
	if bytes.is_empty():
		push_warning("WavLoader: empty " + label)
		return null
	var tmp := "user://_incoming.wav"
	var out := FileAccess.open(tmp, FileAccess.WRITE)
	if out == null:
		push_warning("WavLoader: cannot write scratch for " + label)
		return null
	out.store_buffer(bytes)
	out.close()
	return load_file(tmp)


static func load_file(path: String) -> AudioStreamWAV:
	var f := FileAccess.open(path, FileAccess.READ)
	if f == null:
		push_warning("WavLoader: cannot open " + path)
		return null
	var riff := f.get_buffer(4).get_string_from_ascii()
	if riff != "RIFF":
		push_warning("WavLoader: not RIFF " + path)
		return null
	var _riff_size := f.get_32()
	var wave := f.get_buffer(4).get_string_from_ascii()
	if wave != "WAVE":
		return null
	var fmt_channels := 1
	var fmt_rate := 22050
	var fmt_bits := 16
	var fmt_format := 1
	var data := PackedByteArray()
	while f.get_position() + 8 <= f.get_length():
		var chunk_id := f.get_buffer(4).get_string_from_ascii()
		var chunk_size := f.get_32()
		var next := f.get_position() + chunk_size
		if next > f.get_length():
			break
		if chunk_id == "fmt ":
			fmt_format = f.get_16()
			fmt_channels = f.get_16()
			fmt_rate = f.get_32()
			var _byte_rate := f.get_32()
			var _align := f.get_16()
			fmt_bits = f.get_16()
		elif chunk_id == "data":
			data = f.get_buffer(chunk_size)
			break
		f.seek(next)
		if chunk_size % 2 == 1:
			f.seek(f.get_position() + 1)
	if data.is_empty():
		return null
	var stream := AudioStreamWAV.new()
	stream.data = data
	stream.mix_rate = fmt_rate
	stream.stereo = fmt_channels > 1
	match fmt_bits:
		8:
			stream.format = AudioStreamWAV.FORMAT_8_BITS
		32:
			stream.format = AudioStreamWAV.FORMAT_IMA_ADPCM if fmt_format == 17 else AudioStreamWAV.FORMAT_16_BITS
		_:
			stream.format = AudioStreamWAV.FORMAT_16_BITS
	if fmt_format == 3:
		# IEEE float — Godot WAV stream is PCM. Skip rather than crash.
		push_warning("WavLoader: float WAV unsupported " + path)
		return null
	return stream
