-- Mo Feng Blade settings. Lives in ReplicatedStorage.MoFengSword.Config.
-- Safe to edit: re-running the installer keeps an existing Config.

local Config = {}

-- "Cyan" (Mo Feng) or "Gold". A Tool can also override this with its "Theme" attribute.
Config.DefaultTheme = "Cyan"

Config.Themes = {
	Cyan = {
		Primary = Color3.fromRGB(0, 190, 255), -- aura, trails, crystal edges
		Core = Color3.fromRGB(205, 255, 255), -- hot centre of every effect
		Vein = Color3.fromRGB(40, 255, 235), -- glowing cracks, wisps
		Accent = Color3.fromRGB(140, 95, 255), -- gems
		Hilt = "Silver",
	},
	Gold = {
		Primary = Color3.fromRGB(255, 160, 25),
		Core = Color3.fromRGB(255, 246, 200),
		Vein = Color3.fromRGB(255, 205, 70),
		Accent = Color3.fromRGB(255, 90, 20),
		Hilt = "Gold",
	},
}

Config.Combat = {
	SwingCooldown = 0.38, -- seconds between clicks
	ComboReset = 1.0, -- idle time before the combo goes back to swing 1
	SwingDamage = { 12, 12, 18 }, -- per combo step
	HitDelay = 0.12, -- when the hitbox checks, after the click
	SwingRange = 7, -- hitbox depth in front of the player (studs)
	SwingWidth = 7,
	SwingHeight = 6,

	SpecialCooldown = 6,
	SpecialWindup = 0.35, -- charge time before the big slash lands
	SpecialDamage = 35,
	SpecialRange = 14,
	SpecialWidth = 16,

	DamageHumanoids = true, -- set false if your game handles damage itself (see SwordHit)
	FriendlyFire = false, -- with Teams, teammates can't hurt each other
}

-- Keys / buttons for the special attack (a touch button is added on mobile).
-- Right mouse is left out on purpose: Roblox uses it to turn the camera.
Config.SpecialInputs = { Enum.KeyCode.E, Enum.KeyCode.ButtonY }

-- Optional custom animations ("rbxassetid://123"). Leave empty to use Roblox's
-- built-in tool slash / lunge animations.
Config.Animations = {
	Swing = {}, -- e.g. { "rbxassetid://1", "rbxassetid://2", "rbxassetid://3" }
	Special = "",
}

-- Roll of the slash arc for each combo step (degrees). 90 = straight down.
Config.SlashAngles = { 70, -65, 95 }

Config.Sounds = {
	Equip = "rbxasset://sounds/unsheath.wav",
	Swing = "rbxasset://sounds/swordslash.wav",
	Special = "rbxasset://sounds/swordlunge.wav",
	Impact = "",
}

-- Paste uploaded image IDs here to override the textures that came with the import,
-- e.g. Glow = "rbxassetid://1234567". Keys: Glow Spark Star Ember Smoke Flash
-- RingSprite Wisp Beam Lightning Trail
Config.Textures = {}

-- Used when a texture is missing (built into every Roblox client).
Config.FallbackTextures = {
	Glow = "rbxasset://textures/particles/sparkles_main.dds",
	Smoke = "rbxasset://textures/particles/smoke_main.dds",
	Wisp = "rbxasset://textures/particles/fire_main.dds",
	Default = "rbxasset://textures/particles/sparkles_main.dds",
}

Config.VFX = {
	IdleRange = 140, -- idle extras (rocks, lightning) only run when the camera is this close
	OrbitRocks = 3,
	Lightning = true,
	ScreenFlash = true, -- special attack flash for players near the impact
	CameraShake = true, -- special attack shake for the attacker
	SlashRadius = 4.2, -- studs
	SpecialSlashRadius = 8,
	ShockwaveRadius = 16,
}

return Config
