package tuc.isse.projekt01.model;

/**
 * Represents a single marble on the board.
 * Tasks (b) and (c). That is the Game pieces.
 * Storing Color, Role and Winner.
 * toString method used to represent the Color and resident of player
 * @author Haris Masood <haris.masood@tu-clausthal.de>
 * @version 1.0
 *
 */
/**
 * Continue working on Haris' previous work
 * xiajiong.xu@tu-clausthal.de
 * Vorname: Xiajiong
 * Nachname: Xu
 */
public class Ball {

    // 1. Attributes (Data)
    private Color color;
    private Role role;
    // private Winner winner; // not required in this class

    /**
     * 2. Constructor (Setup)
     * @param color The team color (BLACK/WHITE)
     * @param role The role (KING/RESIDENT)
     * This runs when we type: new Ball(Color.BLACK, Role.KING);
     */
    public Ball(Color color, Role role) {
        this.color = color;
        this.role = role;
        // Usually, the ball itself doesn't hold the 'Winner' state of the game,
        // we initialize it.
        // this.winner = Winner.NONE; // not required
    }

    /**
     * 3. Getters (So other classes can read these values)
     * @return The color of this ball (WHITE or BLACK)
     */
    public Color getColor() { return color; }
    
    /**
     * Get the role of this ball
     * @return The role (KING or RESIDENT)
     */
    public Role getRole() { return role; }

    /**
     * Task c: Visual Representation
     * Returns the string symbol for the ball based on the PDF table.
     */
    @Override
    public String toString() {
        if (this.color == Color.BLACK) {
            if (this.role == Role.RESIDENT) return "B"; // Black Resident
            else return "X";                            // Black King
        } else {
            // WHITE
            if (this.role == Role.RESIDENT) return "W"; // White Resident
            // Fixed： NOT 0 BUT O
            else return "O";                            // White King (Using Zero as per table text)
        }
    }
}