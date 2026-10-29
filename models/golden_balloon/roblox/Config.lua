-- Golden King Balloon settings. Lives in ReplicatedStorage.GoldenKingBalloon.Config.
-- Safe to edit: re-running the installer keeps an existing Config.

local Config = {}

-- ---------------------------------------------------------------- who has it

-- A player wears the balloon while this attribute on their Player is "GoldenKingBalloon".
-- Your shop / inventory can set it, e.g. player:SetAttribute("EquippedBalloon", "GoldenKingBalloon"),
-- or call BalloonCosmetic.Equip(player) / .Unequip(player) from a server script.
Config.EquipAttribute = "EquippedBalloon"
-- Give it to everyone while you test in Studio (never in a live game).
Config.AutoEquipInStudio = true
-- Give it to every player in live games too (leave false if it's a shop item).
Config.AutoEquipEveryone = false

-- ---------------------------------------------------------------- where it floats

-- Studs from the player's HumanoidRootPart: X = to their right, Y = up, Z = behind them.
-- It's scaled with the character's height, so it sits the same on small and tall R15 avatars.
Config.Offset = Vector3.new(1.6, 3.6, 1.9)

Config.Float = {
	BobHeight = 0.18, -- studs up and down
	BobSpeed = 0.32, -- bobs per second
	Sway = 0.08, -- studs side to side
	SwaySpeed = 0.21,
	Tilt = 2.5, -- degrees of gentle rocking
	FollowStiffness = 40, -- how tightly it follows (lower = floatier, more lag when they start or stop)
	FollowDamping = 0.8, -- 1 = no overshoot, lower = a little bounce
	LeanIntoMotion = 0.012, -- how much it leans when the player runs (radians per stud/s)
	MaxLean = 12, -- degrees
	TurnSpeed = 7, -- how quickly it turns to face the way the player faces
	WingFlap = 3.5, -- degrees the wings rise and fall
	WingFold = 2.0, -- degrees they sweep back and forward
	WingSpeed = 0.42, -- flaps per second
	AnimateRange = 150, -- only animate balloons this close to the camera
	FloatAwayOnDeath = true, -- the balloon drifts up and away when its player dies
}

-- ---------------------------------------------------------------- how it looks

Config.Colors = {
	Balloon = Color3.fromRGB(255, 196, 30), -- only used if the balloon's texture didn't import
	Gold = Color3.fromRGB(255, 190, 40), -- crown and nozzle, if their texture didn't import
	Gem = Color3.fromRGB(255, 214, 40), -- the crown's gems
	Feather = Color3.fromRGB(255, 246, 225), -- wings, if their texture didn't import
	String = Color3.fromRGB(255, 250, 238),
	Light = Color3.fromRGB(255, 214, 120), -- the warm light round the balloon
}

-- "Metallic" (the imported glossy gold texture, the default) or "Glow" (bright Neon gold).
Config.BalloonStyle = "Metallic"
-- "Glass" (sparkling yellow gems, the default), "Neon" (glowing) or "Texture".
Config.GemStyle = "Glass"
Config.GemTransparency = 0.12
-- "Texture" (white / ivory feathers with gold bases, the default) or "Glow" (glowing white Neon).
Config.WingStyle = "Texture"

-- Optional: tie the string to the player's right hand with a curved beam instead of the
-- hanging string.
Config.TetherToHand = false

-- Paste uploaded image IDs here to override the imported textures, e.g. Sparkle = "rbxassetid://1".
-- Keys: Glow GlowGold GlowSoft Rays Trail Sparkle Star Mote Feather Swirl
Config.Textures = {}

Config.FallbackTextures = {
	Default = "rbxasset://textures/particles/sparkles_main.dds",
}

-- ---------------------------------------------------------------- the golden aura

Config.VFX = {
	Aura = true, -- the whole golden aura on / off
	Trails = true, -- the swirling golden energy trails
	TrailSpin = 22, -- degrees per second the trails turn round the balloon
	TrailFlow = 0.5, -- how fast light flows along them
	Streams = 2, -- bright streaks racing round the trails
	StreamSpeed = 0.45, -- laps per second
	Feathers = true, -- the golden feathers floating off it
	LightPulse = true, -- the glow gently breathes
}

return Config
